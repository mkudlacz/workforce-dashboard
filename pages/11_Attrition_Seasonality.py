import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from db import run_query
from filters import render_sidebar_filter

st.title("Attrition Seasonality")

start_date, end_date = render_sidebar_filter()

st.markdown(
    "Voluntary departures aren't random — they cluster. Across every year in this dataset, "
    "two structural patterns dominate: a Q4 freeze where quit rates fall sharply through "
    "November and December, and a Q1 surge that builds from January and peaks in March. "
    "A secondary dip runs through July and August. BLS JOLTS data documents the same rhythm "
    "in aggregate US quit rates — the seasonality is structural, not coincidental."
)

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@st.cache_data
def load_monthly_attrition(start_date: str, end_date: str) -> pd.DataFrame:
    return run_query(f"""
        WITH first_snap AS (
            SELECT strftime('%Y-%m', SnapDate) AS ym,
                   MIN(SnapDate)               AS first_date
            FROM snapshots
            WHERE SnapDate BETWEEN '{start_date}' AND '{end_date}'
            GROUP BY ym
        ),
        headcount AS (
            SELECT f.ym, COUNT(*) AS hc
            FROM first_snap f
            JOIN snapshots s ON s.SnapDate = f.first_date AND s.Status = 'Active'
            GROUP BY f.ym
        ),
        exits AS (
            SELECT strftime('%Y-%m', SnapDate)         AS ym,
                   strftime('%Y', SnapDate)             AS yr,
                   CAST(strftime('%m', SnapDate) AS INTEGER) AS mo,
                   SUM(CASE WHEN ResignationType = 'Voluntary' THEN 1 ELSE 0 END) AS vol_exits
            FROM snapshots
            WHERE Status = 'Terminated'
              AND SnapDate BETWEEN '{start_date}' AND '{end_date}'
            GROUP BY ym
        )
        SELECT e.ym, e.yr, e.mo, h.hc, e.vol_exits,
               ROUND(100.0 * e.vol_exits / h.hc, 3) AS vol_pct
        FROM exits e
        JOIN headcount h USING(ym)
        ORDER BY e.ym
    """)


df = load_monthly_attrition(start_date, end_date)
df["month_name"] = df["mo"].apply(lambda x: MONTH_NAMES[x - 1])

monthly_avg = (
    df.groupby(["mo", "month_name"])["vol_pct"]
    .mean()
    .reset_index()
    .sort_values("mo")
)
grand_mean = monthly_avg["vol_pct"].mean()

# Color bars: above/below mean by >8%
def bar_color(v):
    if v >= grand_mean * 1.08:
        return '#C9503A'   # dark coral — elevated
    if v <= grand_mean * 0.92:
        return '#81B29A'   # sage — suppressed
    return '#5A9DC0'       # light blue — neutral

monthly_avg["color"] = monthly_avg["vol_pct"].apply(bar_color)

# ── Layout ────────────────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Average Voluntary Quit Rate by Month")

    fig_bar = go.Figure(go.Bar(
        x=monthly_avg["month_name"],
        y=monthly_avg["vol_pct"],
        marker_color=monthly_avg["color"].tolist(),
        hovertemplate="%{x}: %{y:.2f}%<extra></extra>",
    ))
    fig_bar.add_hline(
        y=grand_mean,
        line_dash="dash",
        line_color="gray",
        line_width=1.5,
    )
    fig_bar.add_annotation(
        x=MONTH_NAMES[-1], y=grand_mean,
        text=f"Mean: {grand_mean:.2f}%",
        showarrow=False, yshift=10,
        font=dict(size=10, color="gray"),
        xanchor="right",
    )
    fig_bar.update_layout(
        height=400,
        margin=dict(t=10, b=10, l=10, r=10),
        yaxis_title="Avg Vol Quit Rate (%)",
        xaxis=dict(categoryorder="array", categoryarray=MONTH_NAMES),
        showlegend=False,
    )
    st.plotly_chart(fig_bar, use_container_width=True)
    st.caption(
        "Average monthly voluntary quit rate. The dashed line marks the annual mean. "
        "January and March run nearly as high as each other — the Q1 elevation is the "
        "signal, not a single calendar date."
    )

with col2:
    st.subheader("Year-over-Year Seasonal Pattern")

    pivot = df.pivot_table(index="yr", columns="mo", values="vol_pct", aggfunc="mean")
    pivot.columns = [MONTH_NAMES[c - 1] for c in pivot.columns]
    # Reindex to ensure all 12 months present and in order
    pivot = pivot.reindex(columns=MONTH_NAMES)

    fig_heat = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale=[[0, '#81B29A'], [0.5, '#F2CC8F'], [1, '#C9503A']],
        hovertemplate="%{y} %{x}: %{z:.2f}%<extra></extra>",
        colorbar=dict(title="Vol Quit %", thickness=12, len=0.8),
    ))
    fig_heat.update_layout(
        height=400,
        margin=dict(t=10, b=10, l=10, r=10),
        yaxis=dict(type="category", autorange="reversed"),
        xaxis=dict(side="top"),
    )
    st.plotly_chart(fig_heat, use_container_width=True)
    st.caption(
        "Year-over-year consistency of the seasonal pattern. The Q4 trough and Q1 elevation "
        "are stable across macro cycles — they hold even through the COVID shock and the "
        "2022–2023 tech downturn, suggesting these rhythms operate independently of broader "
        "market conditions."
    )

# ── Callouts ──────────────────────────────────────────────────────────────────
st.divider()

st.info(
    "**The Q4 freeze and Q1 thaw**\n\n"
    "December and November are reliably low-departure months — not because engagement improves, "
    "but because year-end compensation events (e.g., unvested equity, pending annual bonus) "
    "suppress the decision to leave. The mechanism runs in reverse in Q1: once those events "
    "clear, the optionality that was locked up is suddenly liquid. **The practical implication**: "
    "retention conversations held in Q3 land in a window when employees are still anchored. "
    "By January, the calculus has often already shifted."
)

st.info(
    "**A note on who leaves in Q1**\n\n"
    "The year-end freeze is sharpest for top performers — employees rated Exceeds Expectations "
    "leave in December at roughly half the rate of other months. The mechanism is straightforward: "
    "they have the most to lose by leaving before compensation events (e.g., unvested equity, "
    "pending annual bonus) clear. The corollary is less comfortable. Once those events pass, "
    "their exits concentrate in Q1 through early Q2 at a slightly higher rate than any other "
    "rating group. High performers don't just leave more — they leave on a schedule. "
    "We'll return to this in the performance and attrition section."
)
