import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from db import run_query, PRIMARY, PRIMARY_DK, SAGE, RIF_COLOR, DEPT_COLORS
from filters import render_sidebar_filter

st.title("Org Shape Over Time")

start_date, end_date = render_sidebar_filter()

st.markdown(
    "Organizations accumulate structural debt the same way they accumulate technical debt — "
    "incrementally, invisibly, and faster during periods of rapid growth. The shape of this "
    "organization's hierarchy has changed meaningfully across its eleven-year arc: flatter "
    "during growth, steeper after layoffs, with manager density and span of control "
    "responding to headcount shocks with a predictable lag. These charts make the structural "
    "evolution visible at the org level and, where relevant, by department."
)

RIF_DATES = [
    ("2020-09-14", "2020 RIF"),
    ("2022-11-28", "2022 RIF"),
    ("2023-01-02", "2023 RIF"),
]


@st.cache_data
def load_org_shape_weekly(start_date: str, end_date: str) -> pd.DataFrame:
    return run_query(f"""
        SELECT
            SnapDate,
            SUM(CASE WHEN Status='Active' THEN 1 ELSE 0 END)                          AS total_hc,
            SUM(CASE WHEN Status='Active' AND IsManager=1 THEN 1 ELSE 0 END)           AS managers,
            SUM(CASE WHEN Status='Active' AND IsManager=0 THEN 1 ELSE 0 END)           AS ics,
            AVG(CASE WHEN Status='Active' AND IsManager=1 THEN 1.0 ELSE NULL END)      AS mgr_frac_raw
        FROM snapshots
        WHERE SnapDate BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY SnapDate
        ORDER BY SnapDate
    """)


@st.cache_data
def load_span_weekly(start_date: str, end_date: str) -> pd.DataFrame:
    """Avg span of control = avg direct-report count per active manager, by week."""
    return run_query(f"""
        WITH mgr_reports AS (
            SELECT SnapDate, ManagerID, COUNT(*) AS direct_reports
            FROM snapshots
            WHERE Status='Active' AND ManagerID IS NOT NULL
              AND SnapDate BETWEEN '{start_date}' AND '{end_date}'
            GROUP BY SnapDate, ManagerID
        )
        SELECT SnapDate, AVG(direct_reports) AS avg_span
        FROM mgr_reports
        GROUP BY SnapDate
        ORDER BY SnapDate
    """)


@st.cache_data
def load_layer_mix_annual(start_date: str, end_date: str) -> pd.DataFrame:
    """% of active HC at each org layer, sampled once per year (first snap in Jan)."""
    return run_query(f"""
        WITH jan_snaps AS (
            SELECT strftime('%Y', SnapDate) AS yr, MIN(SnapDate) AS snap
            FROM snapshots
            WHERE SnapDate BETWEEN '{start_date}' AND '{end_date}'
              AND strftime('%m', SnapDate) = '01'
            GROUP BY yr
        )
        SELECT j.yr, s.OrgLayer,
               COUNT(*) AS hc
        FROM jan_snaps j
        JOIN snapshots s ON s.SnapDate = j.snap AND s.Status='Active'
        WHERE s.OrgLayer IS NOT NULL
        GROUP BY j.yr, s.OrgLayer
        ORDER BY j.yr, s.OrgLayer
    """)


@st.cache_data
def load_span_by_dept(start_date: str, end_date: str) -> pd.DataFrame:
    """Average span of control per department at latest snapshot."""
    return run_query(f"""
        WITH latest AS (
            SELECT MAX(SnapDate) AS snap
            FROM snapshots
            WHERE SnapDate <= '{end_date}'
        ),
        mgr_reports AS (
            SELECT s.Department, s.ManagerID, COUNT(*) AS direct_reports
            FROM snapshots s, latest l
            WHERE s.SnapDate = l.snap
              AND s.Status='Active'
              AND s.ManagerID IS NOT NULL
            GROUP BY s.Department, s.ManagerID
        )
        SELECT Department, AVG(direct_reports) AS avg_span, COUNT(*) AS manager_count
        FROM mgr_reports
        GROUP BY Department
        ORDER BY avg_span DESC
    """)


df_weekly = load_org_shape_weekly(start_date, end_date)
df_span   = load_span_weekly(start_date, end_date)
df_layers = load_layer_mix_annual(start_date, end_date)
df_dept   = load_span_by_dept(start_date, end_date)

df_weekly['SnapDate'] = pd.to_datetime(df_weekly['SnapDate'])
df_span['SnapDate']   = pd.to_datetime(df_span['SnapDate'])
df_weekly['mgr_pct']  = (df_weekly['managers'] / df_weekly['total_hc'] * 100).round(2)
df_weekly['ic_mgr_ratio'] = (df_weekly['ics'] / df_weekly['managers'].clip(lower=1)).round(2)


def add_rif_vlines(fig, df_weekly, y_col, label_y_frac=0.95):
    y_max = df_weekly[y_col].max()
    for date_str, label in RIF_DATES:
        ev = pd.Timestamp(date_str)
        if df_weekly['SnapDate'].min() <= ev <= df_weekly['SnapDate'].max():
            fig.add_vline(x=ev.isoformat(), line_dash='dash',
                          line_color=RIF_COLOR, line_width=1, opacity=0.5)
            fig.add_annotation(
                x=ev, y=y_max * label_y_frac,
                text=label, showarrow=False, textangle=-90,
                xanchor='right', font=dict(size=9, color=RIF_COLOR),
            )


# ── Chart 1: Manager % and IC:Mgr ratio ──────────────────────────────────────
st.subheader("Manager Density and IC:Manager Ratio Over Time")

fig_mgr = go.Figure()
fig_mgr.add_trace(go.Scatter(
    x=df_weekly['SnapDate'], y=df_weekly['mgr_pct'],
    mode='lines', name='Manager %',
    line=dict(color=PRIMARY_DK, width=1.5),
    hovertemplate='%{x|%b %Y}: %{y:.1f}% managers<extra></extra>',
    yaxis='y1',
))
fig_mgr.add_trace(go.Scatter(
    x=df_weekly['SnapDate'], y=df_weekly['ic_mgr_ratio'],
    mode='lines', name='IC:Manager ratio',
    line=dict(color=SAGE, width=1.5, dash='dot'),
    hovertemplate='%{x|%b %Y}: %{y:.1f} ICs per manager<extra></extra>',
    yaxis='y2',
))
add_rif_vlines(fig_mgr, df_weekly, 'mgr_pct')
fig_mgr.update_layout(
    height=320,
    margin=dict(t=10, b=10, l=10, r=60),
    xaxis_title='',
    yaxis=dict(title='Manager % of HC', side='left'),
    yaxis2=dict(title='ICs per Manager', side='right', overlaying='y'),
    legend=dict(orientation='h', y=-0.2),
    hovermode='x unified',
)
st.plotly_chart(fig_mgr, use_container_width=True)
st.caption(
    "Manager % (left axis) and IC:Manager ratio (right axis). RIF events visible as "
    "dashed vertical lines. Growth periods tend to compress the ratio as IC hiring outpaces "
    "manager creation; layoffs often spike the manager % temporarily as IC roles are cut first."
)

# ── Chart 2: Avg span of control ──────────────────────────────────────────────
st.subheader("Average Span of Control Over Time")

fig_span = go.Figure()
fig_span.add_trace(go.Scatter(
    x=df_span['SnapDate'], y=df_span['avg_span'],
    mode='lines', name='Avg span',
    line=dict(color=PRIMARY, width=1.5),
    fill='tozeroy', fillcolor='rgba(58,124,165,0.07)',
    hovertemplate='%{x|%b %Y}: avg span %{y:.1f}<extra></extra>',
))
add_rif_vlines(fig_span, df_span, 'avg_span')

# Benchmark bands
fig_span.add_hrect(y0=6, y1=10, fillcolor='rgba(129,178,154,0.08)',
                   line_width=0, annotation_text='Healthy range (6–10)',
                   annotation_position='top right',
                   annotation_font=dict(size=9, color=SAGE))

fig_span.update_layout(
    height=300,
    margin=dict(t=10, b=10, l=10, r=10),
    yaxis_title='Avg Direct Reports per Manager',
    xaxis_title='',
    showlegend=False,
    hovermode='x unified',
)
st.plotly_chart(fig_span, use_container_width=True)
st.caption(
    "Average number of direct reports per active manager, weekly. "
    "The shaded band marks the 6–10 range often cited as operationally healthy for "
    "knowledge-work organizations (Kates & Galbraith, 2007). "
    "Span compression below 6 signals over-management; spikes above 10 signal under-management "
    "and are common in the quarters immediately following a RIF."
)

# ── Chart 3: Layer mix over time ──────────────────────────────────────────────
st.subheader("Org Layer Distribution Over Time")

if not df_layers.empty:
    pivot_layers = df_layers.pivot_table(index='yr', columns='OrgLayer', values='hc', fill_value=0)
    pivot_layers = pivot_layers.div(pivot_layers.sum(axis=1), axis=0) * 100
    layer_cols = sorted(pivot_layers.columns)

    layer_palette = [PRIMARY, PRIMARY_DK, SAGE, '#5A9DC0', '#F2CC8F', '#E07A5F', '#C9503A', '#EC9B80']

    fig_layer = go.Figure()
    for i, col in enumerate(layer_cols):
        fig_layer.add_trace(go.Bar(
            name=f'Layer {col}',
            x=pivot_layers.index.tolist(),
            y=pivot_layers[col].round(1),
            marker_color=layer_palette[i % len(layer_palette)],
            hovertemplate=f'Layer {col}: %{{y:.1f}}%<extra></extra>',
        ))
    fig_layer.update_layout(
        barmode='stack',
        height=320,
        margin=dict(t=10, b=10, l=10, r=10),
        yaxis_title='% of Active Headcount',
        xaxis_title='Year',
        legend=dict(orientation='h', y=-0.25, title='Org Layer'),
        hovermode='x unified',
    )
    st.plotly_chart(fig_layer, use_container_width=True)
    st.caption(
        "Annual snapshot (January) of active headcount distribution by org layer. "
        "Shifts toward deeper layers indicate hierarchy growth during expansion; "
        "layer compression during downsizing is visible as proportional shifts toward "
        "upper layers."
    )

# ── Chart 4: Span by department ───────────────────────────────────────────────
st.subheader("Average Span of Control by Department (Current)")

df_dept_sorted = df_dept.sort_values('avg_span', ascending=True)
fig_dept_span = go.Figure(go.Bar(
    x=df_dept_sorted['avg_span'].round(1),
    y=df_dept_sorted['Department'],
    orientation='h',
    marker_color=[DEPT_COLORS.get(d, '#888') for d in df_dept_sorted['Department']],
    text=df_dept_sorted['avg_span'].apply(lambda v: f"{v:.1f}"),
    textposition='outside',
    hovertemplate='%{y}: avg span %{x:.1f}<extra></extra>',
))
fig_dept_span.add_vline(x=6, line_dash='dot', line_color=SAGE, line_width=1)
fig_dept_span.add_vline(x=10, line_dash='dot', line_color=SAGE, line_width=1)
fig_dept_span.update_layout(
    height=360,
    margin=dict(t=10, b=10, l=10, r=60),
    xaxis_title='Avg Direct Reports per Manager',
    yaxis_title='',
    showlegend=False,
)
st.plotly_chart(fig_dept_span, use_container_width=True)
st.caption(
    "Average span of control by department at the most recent snapshot in the selected range. "
    "Dotted lines mark the 6 and 10 thresholds. Departments below 6 warrant scrutiny for "
    "over-management; those above 10 may have under-invested in management capacity."
)

# ── Callouts ──────────────────────────────────────────────────────────────────
st.divider()

col1, col2 = st.columns(2)

with col1:
    st.info(
        "**Structural lag after RIFs**\n\n"
        "Manager density typically rises in the quarters immediately following a layoff — "
        "not because the organization added managers, but because IC roles were cut faster "
        "than manager roles. The result is a temporarily top-heavy structure: managers "
        "with small or restructured teams, elevated per-manager overhead, and span of "
        "control below the effective range. This structural lag rarely generates urgency "
        "in the RIF post-mortem. It does generate cost and coordination inefficiency — "
        "and it creates pressure to consolidate management layers in the 12–18 months "
        "following the event, often through a second round of involuntary exits."
    )

with col2:
    st.info(
        "**Why org shape matters for people analytics**\n\n"
        "Layer depth and span of control are not just structural preferences — they shape "
        "promotion velocity, communication fidelity, and manager workload. Flat organizations "
        "with wide spans give individual contributors more autonomy and faster feedback loops "
        "but put more strain on managers. Deep hierarchies with narrow spans create more "
        "promotion rungs but slower decision cycles. Neither is inherently better; both "
        "have predictable effects on engagement and attrition that are visible in this data. "
        "The value of tracking org shape over time is that it makes these structural choices — "
        "and their consequences — empirically visible rather than merely asserted."
    )
