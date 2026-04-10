import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from db import run_query, DEPT_COLORS, PRIMARY, RIF_COLOR
from filters import render_sidebar_filter

st.title("Macro Shocks & Survivor Syndrome")

start_date, end_date = render_sidebar_filter()

st.markdown(
    "Three workforce shocks appear in this dataset, each anchored to a real macroeconomic "
    "inflection point: the COVID-19 disruption (Q3 2020), the tech valuation collapse "
    "following rising interest rates (Q4 2022), and the peak tech layoff wave of Q1 2023. "
    "What the headcount numbers don't capture is what happened to the people who stayed. "
    "Research on post-RIF survivor psychology — Brockner (1990, 1992), Datta et al.'s "
    "2010 meta-analysis across 267 studies — consistently documents engagement erosion that "
    "persists well beyond the event itself. The data here confirms that pattern."
)

RIF_EVENTS = [
    {"date": "2020-09-14", "label": "2020 RIF (COVID)", "layoffs": 256},
    {"date": "2022-11-28", "label": "2022 RIF (Rate shock)", "layoffs": 806},
    {"date": "2023-01-02", "label": "2023 RIF (Peak tech layoffs)", "layoffs": 433},
]
RIF_COLORS = {"2020": "#F2CC8F", "2022": "#C9503A", "2023": "#81B29A"}


@st.cache_data
def load_headcount(start_date: str, end_date: str) -> pd.DataFrame:
    return run_query(f"""
        SELECT SnapDate,
               SUM(CASE WHEN Status = 'Active'              THEN 1 ELSE 0 END) AS active_hc,
               SUM(CASE WHEN ResignationType = 'Layoff'     THEN 1 ELSE 0 END) AS layoffs
        FROM snapshots
        WHERE SnapDate BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY SnapDate ORDER BY SnapDate
    """)


@st.cache_data
def load_engagement_weekly(start_date: str, end_date: str) -> pd.DataFrame:
    return run_query(f"""
        SELECT SnapDate, AVG(EngagementIndex) AS avg_eng
        FROM snapshots
        WHERE Status = 'Active'
          AND SnapDate BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY SnapDate ORDER BY SnapDate
    """)


@st.cache_data
def load_layoffs_by_dept() -> pd.DataFrame:
    return run_query("""
        SELECT Department, COUNT(*) AS layoffs
        FROM snapshots WHERE ResignationType = 'Layoff'
        GROUP BY Department ORDER BY layoffs DESC
    """)


hc_df  = load_headcount(start_date, end_date)
eng_df = load_engagement_weekly(start_date, end_date)
dept_df = load_layoffs_by_dept()

hc_df['SnapDate']  = pd.to_datetime(hc_df['SnapDate'])
eng_df['SnapDate'] = pd.to_datetime(eng_df['SnapDate'])

# ── Chart 1: Headcount timeline ───────────────────────────────────────────────
st.subheader("Active Headcount Over Time")

fig_hc = go.Figure()
fig_hc.add_trace(go.Scatter(
    x=hc_df['SnapDate'], y=hc_df['active_hc'],
    mode='lines', name='Active headcount',
    line=dict(color=PRIMARY, width=1.5),
    fill='tozeroy', fillcolor='rgba(99,110,250,0.1)',
    hovertemplate='%{x|%b %Y}: %{y:,}<extra></extra>',
))
for ev in RIF_EVENTS:
    ev_date = pd.Timestamp(ev['date'])
    if pd.Timestamp(start_date) <= ev_date <= pd.Timestamp(end_date):
        fig_hc.add_vline(x=ev_date.isoformat(), line_dash='dash',
                         line_color=RIF_COLOR, line_width=1.5, opacity=0.7)
        fig_hc.add_annotation(
            x=ev_date, y=hc_df['active_hc'].max() * 0.97,
            text=ev['label'], showarrow=False,
            textangle=-90, xanchor='right',
            font=dict(size=10, color=RIF_COLOR),
        )
fig_hc.update_layout(
    height=280, margin=dict(t=10, b=10, l=10, r=10),
    yaxis_title='Active Headcount',
    xaxis_title='',
    showlegend=False,
    hovermode='x unified',
)
st.plotly_chart(fig_hc, use_container_width=True)
st.caption(
    "Org-wide active headcount, 2015–2026. Dashed lines mark the three RIF events. "
    "The 2022–2023 window represents the most severe shock: two events within five weeks, "
    "collectively eliminating nearly 1,250 positions."
)

# ── Chart 2: Indexed engagement event study ───────────────────────────────────
st.subheader("Engagement Trajectory Around Each RIF")
st.markdown(
    "Engagement change relative to the four-week pre-RIF baseline (0 = pre-event average). "
    "Positive values indicate engagement above baseline; negative values indicate erosion."
)

event_traces = []
for ev in RIF_EVENTS:
    rif_date = pd.Timestamp(ev['date'])
    window = eng_df[
        (eng_df['SnapDate'] >= rif_date - pd.Timedelta(weeks=16)) &
        (eng_df['SnapDate'] <= rif_date + pd.Timedelta(weeks=40))
    ].copy()
    window['week'] = ((window['SnapDate'] - rif_date).dt.days / 7).round().astype(int)
    baseline = window[window['week'].between(-4, -1)]['avg_eng'].mean()
    window['rel_eng'] = window['avg_eng'] - baseline
    event_traces.append((ev, window))

fig_idx = go.Figure()
fig_idx.add_hline(y=0, line_dash='dot', line_color='gray', line_width=1)

year_colors = {"2020": "#F2CC8F", "2022": "#C9503A", "2023": "#81B29A"}
for ev, window in event_traces:
    yr = ev['date'][:4]
    fig_idx.add_trace(go.Scatter(
        x=window['week'], y=window['rel_eng'],
        mode='lines', name=ev['label'],
        line=dict(color=year_colors[yr], width=2),
        hovertemplate=f"{ev['label']}<br>Week %{{x}}: %{{y:+.2f}} pts<extra></extra>",
    ))

fig_idx.add_vline(x=0, line_dash='dash', line_color='gray', line_width=1, opacity=0.5)
fig_idx.update_layout(
    height=380,
    margin=dict(t=10, b=10, l=10, r=10),
    xaxis_title='Weeks Relative to RIF Event',
    yaxis_title='Engagement Change (pts)',
    legend=dict(orientation='h', y=-0.18),
    hovermode='x unified',
)
st.plotly_chart(fig_idx, use_container_width=True)
st.caption(
    "The 2022 and 2023 events each produced a 3–5 point drop within weeks, with meaningful "
    "recovery beginning around week 10–12 and substantially complete by week 36–40. "
    "The 2020 event shows a different profile: engagement holds — even ticks slightly upward — "
    "before beginning a sustained decline roughly three months after the event. This pattern "
    "can emerge when layoffs are perceived as procedurally fair, or when the broader climate "
    "is uncertain enough that survivors feel relief at keeping their jobs rather than guilt "
    "about losing colleagues. Sometimes called *survivor relief*, it doesn't prevent "
    "engagement erosion — it defers it."
)

# ── Chart 3: Layoffs by department ────────────────────────────────────────────
st.subheader("Layoff Distribution by Department")

dept_sorted = dept_df.sort_values('layoffs', ascending=True)
fig_dept = go.Figure(go.Bar(
    x=dept_sorted['layoffs'],
    y=dept_sorted['Department'],
    orientation='h',
    marker_color=[DEPT_COLORS.get(d, '#888') for d in dept_sorted['Department']],
    hovertemplate='%{y}: %{x:,} layoffs<extra></extra>',
    text=dept_sorted['layoffs'],
    textposition='outside',
))
fig_dept.update_layout(
    height=340,
    margin=dict(t=10, b=10, l=10, r=80),
    xaxis_title='Total Layoffs (all RIF events)',
    yaxis_title='',
    showlegend=False,
)
st.plotly_chart(fig_dept, use_container_width=True)

# ── Callouts ──────────────────────────────────────────────────────────────────
st.divider()

col1, col2 = st.columns(2)

with col1:
    st.info(
        "**The engagement cost of a RIF**\n\n"
        "The 2022 event reduced org-wide engagement by approximately 4–5 points relative "
        "to pre-event baseline — equivalent to nearly half the gap between the highest- and "
        "lowest-scoring departments in this workforce. Recovery is real but slow: meaningful "
        "uptick begins around week 10–12, and the pre-RIF baseline isn't substantially "
        "restored until week 36–40. Datta et al.'s meta-analysis places survivor effects on "
        "organizational commitment at 12–18 months; this dataset's trajectory is consistent "
        "with the lower bound. The practical implication: the year following a significant "
        "RIF is an elevated voluntary flight-risk window, even for employees not directly cut."
    )

with col2:
    st.info(
        "**Who absorbs the cuts**\n\n"
        "G&A and operational functions — Marketing, Sales, Finance, HR — account for the "
        "largest share of layoffs in absolute terms, while Engineering, Product, and Data "
        "Analytics carry the lowest exposure. This is the standard tech-downturn playbook: "
        "protect technical capability, reduce overhead. The downstream consequence is often "
        "underappreciated: the surviving G&A population is left carrying elevated workload "
        "with a simultaneously depressed engagement baseline — a compounding effect that "
        "rarely appears in restructuring ROI calculations."
    )
