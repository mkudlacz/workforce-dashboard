import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from db import run_query, DEPT_COLORS
from filters import render_sidebar_filter

st.set_page_config(page_title="Org Health", page_icon="🏢", layout="wide")
st.title("🏢 Org Health")

start_date, end_date = render_sidebar_filter()


@st.cache_data
def load_data(start_date: str, end_date: str):
    # All "point-in-time" charts use the last available snapshot within the period.
    as_of = f"(SELECT MAX(SnapDate) FROM snapshots WHERE SnapDate <= '{end_date}')"

    # Span of control: direct reports per manager, as of end of period
    span = run_query(f"""
        SELECT ManagerID, COUNT(*) AS direct_reports
        FROM snapshots
        WHERE SnapDate = {as_of}
          AND Status = 'Active'
          AND ManagerID IS NOT NULL
          AND ManagerID != 'Board'
        GROUP BY ManagerID
    """)

    # Org layer distribution by department, as of end of period
    layers = run_query(f"""
        SELECT Department, OrgLayer, IsManager, COUNT(*) AS n
        FROM snapshots
        WHERE SnapDate = {as_of}
          AND Status = 'Active'
        GROUP BY Department, OrgLayer, IsManager
        ORDER BY Department, OrgLayer, IsManager
    """)

    # Manager % over time (monthly)
    mgr_time = run_query(f"""
        SELECT SnapDate,
               SUM(CASE WHEN IsManager = 1 THEN 1 ELSE 0 END) AS mgr_count,
               COUNT(*) AS total
        FROM snapshots
        WHERE Status = 'Active'
          AND SnapDate BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY SnapDate
        ORDER BY SnapDate
    """)
    mgr_time['SnapDate'] = pd.to_datetime(mgr_time['SnapDate'])
    mgr_time['mgr_pct']  = mgr_time['mgr_count'] / mgr_time['total'] * 100

    # Layer summary (as of end of period)
    layer_summary = run_query(f"""
        SELECT s.OrgLayer, COUNT(*) AS n
        FROM snapshots s
        WHERE s.SnapDate = {as_of}
          AND s.Status = 'Active'
        GROUP BY s.OrgLayer ORDER BY s.OrgLayer
    """)

    # Layer x IsManager summary for pyramid segments
    layer_mgr = run_query(f"""
        SELECT OrgLayer, IsManager, COUNT(*) AS n
        FROM snapshots
        WHERE SnapDate = {as_of}
          AND Status = 'Active'
        GROUP BY OrgLayer, IsManager
        ORDER BY OrgLayer, IsManager
    """)

    # Orphan check — always uses current employees table (data quality)
    orphans = run_query("""
        SELECT COUNT(*) AS n FROM employees e
        WHERE e.ManagerID IS NOT NULL
          AND e.ManagerID != 'Board'
          AND e.ManagerID NOT IN (SELECT EmployeeID FROM employees)
          AND e.Status = 'Active'
    """).iloc[0, 0]

    return span, layers, mgr_time, layer_summary, layer_mgr, orphans


span, layers, mgr_time, layer_summary, layer_mgr, orphans = load_data(start_date, end_date)

# ── Key metrics ───────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Median Span of Control",  f"{int(span['direct_reports'].median())} reports")
c2.metric("Max Span of Control",     f"{int(span['direct_reports'].max())} reports")
c3.metric("Manager % (end of period)", f"{mgr_time.iloc[-1]['mgr_pct']:.1f}%")
c4.metric("Orphaned Employees",      str(int(orphans)))

st.divider()

# ── Chart 1: Span of control distribution ────────────────────────────────────
st.subheader(f"Span of Control Distribution (as of {end_date})")
fig1 = px.histogram(
    span, x='direct_reports', nbins=30,
    labels={'direct_reports': 'Direct Reports', 'count': 'Managers'},
    color_discrete_sequence=['#636EFA'],
)
fig1.update_layout(bargap=0.05)
st.plotly_chart(fig1, use_container_width=True)

# ── Chart 2: Org layer by department ─────────────────────────────────────────
st.subheader(f"Org Layer Distribution by Department (as of {end_date})")
layers['OrgLayer'] = layers['OrgLayer'].astype(str)
fig2 = px.bar(
    layers, x='Department', y='n', color='OrgLayer',
    labels={'n': 'Employees', 'OrgLayer': 'Layer', 'Department': ''},
    barmode='stack',
    category_orders={'OrgLayer': [str(i) for i in range(1, 10)]},
)
fig2.update_layout(legend_title='Org Layer', legend=dict(orientation='h', y=-0.2))
st.plotly_chart(fig2, use_container_width=True)

# ── Chart 3: Manager % over time ──────────────────────────────────────────────
st.subheader("Manager % of Active Workforce Over Time")
monthly_mgr = (
    mgr_time.set_index('SnapDate')['mgr_pct']
    .resample('ME').mean()
    .reset_index()
)
fig3 = px.line(
    monthly_mgr, x='SnapDate', y='mgr_pct',
    labels={'SnapDate': '', 'mgr_pct': 'Manager %'},
)
fig3.update_traces(line_color='#AB63FA')
fig3.add_hline(y=25, line_dash='dot', line_color='orange',
               annotation_text='25% upper bound', annotation_position='bottom right')
fig3.add_hline(y=10, line_dash='dot', line_color='green',
               annotation_text='10% lower bound', annotation_position='top right')
fig3.update_layout(hovermode='x unified')
st.plotly_chart(fig3, use_container_width=True)

# ── Current layer breakdown table ─────────────────────────────────────────────
st.subheader(f"Active Employees by Org Layer (as of {end_date})")
st.dataframe(
    layer_summary.rename(columns={'OrgLayer': 'Layer', 'n': 'Employees'}),
    hide_index=True, use_container_width=False,
)

st.divider()

# ── Chart 4: Whole-org layer distribution (centered pyramid) ─────────────────
st.subheader(f"Org Layer Distribution — Whole Org (as of {end_date})")
ls = layer_summary.sort_values('OrgLayer').copy()
# numeric y-axis: range=[8.5, 0.5] puts Layer 1 at top, Layer 8 at bottom
LAYER_YAXIS = dict(
    title='Layer',
    range=[8.5, 0.5],
    tickmode='linear', tick0=1, dtick=1,
)

pivot4 = (
    layer_mgr.pivot(index='OrgLayer', columns='IsManager', values='n')
    .fillna(0)
    .rename(columns={0: 'ic', 1: 'mgr'})
    .assign(total=lambda d: d['ic'] + d['mgr'])
    .assign(ic_base=lambda d: -d['total'] / 2)
    .assign(mgr_base=lambda d: -d['total'] / 2 + d['ic'])
    .reset_index()
    .sort_values('OrgLayer')
)

fig4 = go.Figure()
fig4.add_trace(go.Bar(
    x=pivot4['ic'], y=pivot4['OrgLayer'],
    base=pivot4['ic_base'].tolist(),
    orientation='h', name='Individual Contributor',
    marker_color='#636EFA',
    text=pivot4['ic'].astype(int), textposition='inside',
))
fig4.add_trace(go.Bar(
    x=pivot4['mgr'], y=pivot4['OrgLayer'],
    base=pivot4['mgr_base'].tolist(),
    orientation='h', name='Manager',
    marker_color='#EF553B',
    text=pivot4['mgr'].astype(int), textposition='inside',
))
fig4.update_layout(
    barmode='overlay',
    yaxis=LAYER_YAXIS,
    xaxis=dict(showticklabels=False, zeroline=True, zerolinecolor='#888', zerolinewidth=1),
    legend=dict(orientation='h', y=-0.15),
    height=350,
)
st.plotly_chart(fig4, use_container_width=True)

# ── Chart 5: Layer distribution by department (centered pyramid per dept) ─────
st.subheader(f"Org Layer Distribution by Department (as of {end_date})")
# layers['OrgLayer'] is already str from chart 2 — cast back to int for numeric axis
layers_int = layers.copy()
layers_int['OrgLayer'] = layers_int['OrgLayer'].astype(int)
depts = sorted(layers_int['Department'].unique())
ncols = 3
nrows = (len(depts) + ncols - 1) // ncols

fig5 = make_subplots(rows=nrows, cols=ncols, subplot_titles=depts)
for i, dept in enumerate(depts):
    row, col = i // ncols + 1, i % ncols + 1
    df_dept = (
        layers_int[layers_int['Department'] == dept]
        .pivot_table(index='OrgLayer', columns='IsManager', values='n', fill_value=0)
        .reindex(columns=[0, 1], fill_value=0)
        .rename(columns={0: 'ic', 1: 'mgr'})
        .assign(total=lambda d: d['ic'] + d['mgr'])
        .assign(ic_base=lambda d: -d['total'] / 2)
        .assign(mgr_base=lambda d: -d['total'] / 2 + d['ic'])
        .reset_index()
        .sort_values('OrgLayer')
    )
    show = (i == 0)  # legend entries only on first subplot
    fig5.add_trace(go.Bar(
        x=df_dept['ic'], y=df_dept['OrgLayer'],
        base=df_dept['ic_base'].tolist(),
        orientation='h', name='Individual Contributor',
        marker_color='#636EFA', legendgroup='ic',
        text=df_dept['ic'].astype(int), textposition='inside',
        showlegend=show,
    ), row=row, col=col)
    fig5.add_trace(go.Bar(
        x=df_dept['mgr'], y=df_dept['OrgLayer'],
        base=df_dept['mgr_base'].tolist(),
        orientation='h', name='Manager',
        marker_color='#EF553B', legendgroup='mgr',
        text=df_dept['mgr'].astype(int), textposition='inside',
        showlegend=show,
    ), row=row, col=col)
    fig5.update_yaxes(
        range=[8.5, 0.5], tickmode='linear', tick0=1, dtick=1,
        title_text='Layer' if col == 1 else '',
        row=row, col=col,
    )
    fig5.update_xaxes(showticklabels=False, zeroline=True, zerolinecolor='#888', row=row, col=col)

fig5.update_layout(barmode='overlay', height=750, legend=dict(orientation='h', y=-0.02))
st.plotly_chart(fig5, use_container_width=True)
