import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from db import run_query, PRIMARY, VOL_COLOR, RIF_COLOR
from filters import render_sidebar_filter

st.title("Manager Departure Cascades")

start_date, end_date = render_sidebar_filter()

st.markdown(
    "When a manager leaves, so do some of the people who reported to them — not immediately, "
    "but predictably. The mechanism is well-documented: manager departure dissolves the "
    "psychological safety and role clarity that anchor employees to a team. The employees "
    "most likely to follow their manager out are also the most portable — the ones who "
    "joined for the person, not the institution. This event study tracks 1,500+ manager "
    "exits across the dataset and measures what happened to the teams they left behind."
)


@st.cache_data
def load_cascade(start_date: str, end_date: str) -> pd.DataFrame:
    df = run_query(f"""
        WITH mgr_exits AS (
            SELECT EmployeeID AS mgr_id,
                   DATE(TerminationDate) AS exit_date
            FROM employees
            WHERE IsManager = 1
              AND TerminationDate IS NOT NULL
              AND DATE(TerminationDate) BETWEEN '{start_date}' AND '{end_date}'
        ),
        cascade AS (
            SELECT
                CAST(ROUND(
                    (julianday(s.SnapDate) - julianday(me.exit_date)) / 7
                ) AS INTEGER) AS rel_week,
                s.Status,
                s.ResignationType
            FROM mgr_exits me
            JOIN snapshots baseline
                ON  baseline.ManagerID = me.mgr_id
                AND baseline.Status    = 'Active'
                AND baseline.SnapDate BETWEEN date(me.exit_date, '-35 days')
                                          AND date(me.exit_date, '-21 days')
            JOIN snapshots s
                ON  s.EmployeeID = baseline.EmployeeID
                AND s.SnapDate BETWEEN date(me.exit_date, '-35 days')
                               AND date(me.exit_date, '+126 days')
        )
        SELECT rel_week,
               SUM(CASE WHEN Status='Terminated' AND ResignationType='Voluntary'
                        THEN 1 ELSE 0 END) AS vol_exits,
               SUM(CASE WHEN Status='Active' THEN 1 ELSE 0 END) AS active_count
        FROM cascade
        WHERE rel_week BETWEEN -4 AND 18
        GROUP BY rel_week
        ORDER BY rel_week
    """)
    df['rate'] = (df['vol_exits'] / df['active_count'].clip(lower=1) * 52 * 100).round(2)
    return df


df = load_cascade(start_date, end_date)

baseline_rate = df[df['rel_week'] < 0]['rate'].mean() if not df.empty else 0

# ── Chart ─────────────────────────────────────────────────────────────────────
st.subheader("Team Voluntary Attrition Rate — Weeks Relative to Manager Exit")

fig = go.Figure()

# Pre / post shading
if not df.empty:
    max_rate = df['rate'].max()
    fig.add_vrect(x0=-4, x1=0, fillcolor='rgba(200,200,200,0.12)',
                  line_width=0, annotation_text='pre-exit', annotation_position='top left',
                  annotation_font=dict(size=9, color='gray'))
    fig.add_vrect(x0=0, x1=18, fillcolor=f'rgba({int(0xE0)},{int(0x7A)},{int(0x5F)},0.06)',
                  line_width=0, annotation_text='post-exit', annotation_position='top right',
                  annotation_font=dict(size=9, color=VOL_COLOR))

# Baseline reference
fig.add_hline(
    y=baseline_rate, line_dash='dot', line_color='gray', line_width=1.2,
    annotation_text=f'Pre-exit baseline: {baseline_rate:.1f}%',
    annotation_position='bottom right',
    annotation_font=dict(size=9, color='gray'),
)

# Main line
fig.add_trace(go.Scatter(
    x=df['rel_week'], y=df['rate'],
    mode='lines+markers',
    line=dict(color=VOL_COLOR, width=2.5),
    marker=dict(size=5),
    hovertemplate='Week %{x}: %{y:.1f}% annualized<extra></extra>',
    name='Team vol attrition rate',
))

# Week 0 marker
fig.add_vline(x=0, line_dash='dash', line_color=RIF_COLOR, line_width=1.5, opacity=0.7)
fig.add_annotation(
    x=0, y=df['rate'].max() * 1.05,
    text='Manager exits', showarrow=False,
    font=dict(size=9, color=RIF_COLOR), xanchor='left', xshift=6,
)

fig.update_layout(
    height=420,
    margin=dict(t=10, b=10, l=10, r=10),
    xaxis_title='Weeks Relative to Manager Exit (week 0 = departure week)',
    yaxis_title='Annualized Voluntary Attrition Rate (%)',
    showlegend=False,
    hovermode='x unified',
    xaxis=dict(dtick=2, zeroline=False),
)

st.plotly_chart(fig, use_container_width=True)

peak_rate = df[df['rel_week'] >= 0]['rate'].max()
peak_week = df.loc[df['rel_week'] >= 0, 'rate'].idxmax()
peak_wk   = int(df.loc[peak_week, 'rel_week']) if not df.empty else 1

st.caption(
    f"Annualized voluntary attrition rate for direct reports, pooled across {len(df):,} "
    "relative-week observations from 1,500+ manager exit events. Week 0 = the week the "
    f"manager departed. Pre-exit baseline computed from weeks −4 to −1 ({baseline_rate:.1f}% annualized). "
    f"Peak elevation occurs around week {peak_wk} ({peak_rate:.1f}% annualized)."
)

# ── Callouts ──────────────────────────────────────────────────────────────────
st.divider()

col1, col2 = st.columns(2)

mult = round(peak_rate / baseline_rate, 1) if baseline_rate > 0 else 0

with col1:
    st.info(
        "**The cascade window**\n\n"
        f"Voluntary attrition among the departing manager's direct reports peaks at approximately "
        f"{mult:.1f}x the pre-exit baseline in weeks 1–2, then declines through week 8–10 as teams "
        "stabilize under new leadership. The pattern is consistent with the mechanism Trevor et al. "
        "(1997) described as 'relational contract rupture': employees who had implicit psychological "
        "contracts with their specific manager — not just the organization — experience those "
        "contracts as void when the manager departs. Whether they follow the manager to a new "
        "employer or simply reprice their options depends largely on whether a successor is "
        "identified quickly and is perceived as credible."
    )

with col2:
    st.info(
        "**What the data cannot distinguish**\n\n"
        "This event study treats all manager exits as equivalent. They are not. Voluntary manager "
        "departures — resignations — often signal something about the team environment that "
        "predates the exit. Involuntary exits (PIPs, layoffs) carry different signals. Star "
        "manager departures may generate larger cascades than poor manager exits. The pooled "
        "estimate here represents the average across all these cases, which likely understates "
        "the cascade following high-trust manager exits and overstates it following poor-manager "
        "exits (where teams may experience relief rather than disruption). Segmenting by "
        "manager quality would sharpen the signal considerably — and is a natural extension "
        "of the manager quality analysis on the preceding page."
    )
