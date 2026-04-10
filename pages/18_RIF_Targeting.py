import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from db import run_query, DEPT_COLORS, LAYOFF_COLOR, PRIMARY, SAGE
from filters import render_sidebar_filter

st.title("RIF Targeting Patterns")

start_date, end_date = render_sidebar_filter()

st.markdown(
    "Reductions in force are not random. The departments and job bands selected for "
    "disproportionate cuts reflect deliberate prioritization logic — typically some "
    "variant of 'protect technical capability, reduce overhead.' This page tests "
    "whether the layoffs in this dataset follow that pattern by comparing each "
    "department's and band's share of total layoffs against their share of "
    "total active headcount. A ratio above 1.0 means over-targeted; below 1.0 means "
    "under-targeted. The pattern that emerges is recognizable from a decade of "
    "real-world tech restructuring."
)

BAND_ORDER = ['IC1', 'IC2', 'IC3', 'M1', 'M2', 'M3', 'VP']


@st.cache_data
def load_rif_targeting(start_date: str, end_date: str):
    dept = run_query(f"""
        SELECT Department,
               SUM(CASE WHEN ResignationType='Layoff' THEN 1 ELSE 0 END) AS layoffs,
               SUM(CASE WHEN Status='Active'           THEN 1 ELSE 0 END) AS active_weeks
        FROM snapshots
        WHERE SnapDate BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY Department
    """)

    band = run_query(f"""
        SELECT JobBand,
               SUM(CASE WHEN ResignationType='Layoff' THEN 1 ELSE 0 END) AS layoffs,
               SUM(CASE WHEN Status='Active'           THEN 1 ELSE 0 END) AS active_weeks
        FROM snapshots
        WHERE SnapDate BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY JobBand
    """)

    return dept, band


dept_df, band_df = load_rif_targeting(start_date, end_date)

total_layoffs = dept_df['layoffs'].sum()
total_active  = dept_df['active_weeks'].sum()

for df in [dept_df, band_df]:
    df['layoff_share'] = df['layoffs'] / total_layoffs
    df['hc_share']     = df['active_weeks'] / total_active
    df['over_index']   = (df['layoff_share'] / df['hc_share'].clip(lower=1e-6)).round(2)

dept_df = dept_df.sort_values('over_index', ascending=True)
band_df['JobBand'] = pd.Categorical(band_df['JobBand'], categories=BAND_ORDER, ordered=True)
band_df = band_df.sort_values('JobBand')

# ── Chart 1: Dept over-index ──────────────────────────────────────────────────
st.subheader("Layoff Over-Index by Department")
st.caption("Ratio of each department's layoff share to its headcount share. "
           "1.0 = proportional; >1.0 = over-targeted; <1.0 = protected.")

dept_colors = [
    LAYOFF_COLOR if v > 1.1 else (SAGE if v < 0.9 else PRIMARY)
    for v in dept_df['over_index']
]

fig_dept = go.Figure(go.Bar(
    x=dept_df['over_index'],
    y=dept_df['Department'],
    orientation='h',
    marker_color=dept_colors,
    text=dept_df['over_index'].apply(lambda v: f"{v:.2f}x"),
    textposition='outside',
    hovertemplate='%{y}<br>Over-index: %{x:.2f}x<extra></extra>',
))
fig_dept.add_vline(x=1.0, line_dash='dash', line_color='gray', line_width=1.5)
fig_dept.update_layout(
    height=380,
    margin=dict(t=10, b=10, l=10, r=80),
    xaxis_title='Layoff Share ÷ Headcount Share',
    yaxis_title='',
    showlegend=False,
    xaxis=dict(range=[0, dept_df['over_index'].max() * 1.25]),
)
st.plotly_chart(fig_dept, use_container_width=True)

# ── Chart 2: Band over-index ──────────────────────────────────────────────────
st.subheader("Layoff Over-Index by Job Band")

band_colors = [
    LAYOFF_COLOR if v > 1.1 else (SAGE if v < 0.9 else PRIMARY)
    for v in band_df['over_index']
]

fig_band = go.Figure(go.Bar(
    x=band_df['JobBand'].astype(str),
    y=band_df['over_index'],
    marker_color=band_colors,
    text=band_df['over_index'].apply(lambda v: f"{v:.2f}x"),
    textposition='outside',
    hovertemplate='%{x}<br>Over-index: %{y:.2f}x<extra></extra>',
))
fig_band.add_hline(y=1.0, line_dash='dash', line_color='gray', line_width=1.5)
fig_band.update_layout(
    height=340,
    margin=dict(t=10, b=10, l=10, r=10),
    yaxis_title='Layoff Share ÷ Headcount Share',
    xaxis_title='Job Band (IC → VP)',
    showlegend=False,
    yaxis=dict(range=[0, band_df['over_index'].max() * 1.3]),
)
st.plotly_chart(fig_band, use_container_width=True)
st.caption(
    "Layoff concentration by job band. M1 and M2 are the only bands meaningfully above 1.0; "
    "IC bands sit just below proportional; VP is the most protected at 0.64x. "
    "The pattern is middle management absorption, not IC reduction."
)

# ── Scatter: layoff% vs HC% by dept ──────────────────────────────────────────
st.subheader("Layoff Share vs. Headcount Share by Department")

dept_scatter = dept_df.copy()
dept_scatter['layoff_pct'] = (dept_scatter['layoff_share'] * 100).round(1)
dept_scatter['hc_pct']     = (dept_scatter['hc_share']     * 100).round(1)

fig_scat = px.scatter(
    dept_scatter,
    x='hc_pct', y='layoff_pct',
    text='Department',
    color='Department',
    color_discrete_map=DEPT_COLORS,
    labels={'hc_pct': 'Headcount Share (%)', 'layoff_pct': 'Layoff Share (%)'},
    hover_data={'over_index': True},
)
# Diagonal = proportional
max_val = max(dept_scatter['hc_pct'].max(), dept_scatter['layoff_pct'].max()) * 1.1
fig_scat.add_shape(
    type='line', x0=0, y0=0, x1=max_val, y1=max_val,
    line=dict(color='gray', dash='dot', width=1),
)
fig_scat.add_annotation(
    x=max_val * 0.85, y=max_val * 0.75,
    text='Proportional', showarrow=False,
    font=dict(size=9, color='gray'), textangle=-45,
)
fig_scat.update_traces(textposition='top center', marker=dict(size=10))
fig_scat.update_layout(
    height=400,
    margin=dict(t=10, b=10, l=10, r=10),
    showlegend=False,
)
st.plotly_chart(fig_scat, use_container_width=True)
st.caption(
    "Departments above the diagonal were cut at a higher rate than their headcount share; "
    "departments below were relatively protected. The dotted line represents proportional targeting."
)

# ── Callouts ──────────────────────────────────────────────────────────────────
st.divider()

col1, col2 = st.columns(2)

top_over  = dept_df[dept_df['over_index'] > 1].nlargest(3, 'over_index')['Department'].tolist()
top_under = dept_df[dept_df['over_index'] < 1].nsmallest(3, 'over_index')['Department'].tolist()

with col1:
    st.info(
        "**The standard playbook**\n\n"
        "The over-index pattern confirms the conventional tech restructuring approach: "
        "G&A and go-to-market functions absorb disproportionate cuts, while R&D and "
        "technical functions are protected. The economic logic is defensible — revenue "
        "headcount can be rebuilt faster than engineering capability, and revenue teams "
        "are typically oversized relative to pipeline during growth cycles. But the "
        "people analytics consequence is less often modeled: the surviving G&A population "
        "carries both elevated workload and a suppressed engagement baseline simultaneously. "
        "The combination is the period most likely to generate secondary voluntary attrition "
        "in the 6–12 months following a RIF — from employees who weren't cut but now "
        "question whether they should stay."
    )

with col2:
    st.info(
        "**Middle management absorbs the cuts**\n\n"
        "The band pattern here does not follow the conventional IC-reduction playbook. "
        "M1 (1.16x) and M2 (1.08x) are the only bands meaningfully over-indexed; IC bands "
        "are all slightly below 1.0 and essentially proportional; VP is the most protected "
        "tier at 0.64x. This is a flatten-the-middle-management structure, not a "
        "cut-the-bottom pattern. The operational logic is recognizable: M1 and M2 roles "
        "accumulate during growth cycles as team proliferation outpaces consolidation, and "
        "they become visible targets when headcount scrutiny intensifies. The downstream "
        "consequence is a temporarily wider span of control — managers who survive carry "
        "larger teams with less coordination layer — which is visible in the org shape data "
        "on the preceding page."
    )
