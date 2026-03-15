import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
from db import run_query, DEPT_COLORS
from filters import render_sidebar_filter

st.set_page_config(page_title="Headcount", page_icon="📈", layout="wide")
st.title("📈 Headcount & Workforce Composition")

start_date, end_date = render_sidebar_filter()


@st.cache_data
def load_overview():
    """All-time dataset metrics and current active HC by department."""
    emp = run_query("""
        SELECT
            COUNT(*)                                              AS total_ever,
            SUM(CASE WHEN Status='Active'     THEN 1 ELSE 0 END) AS active,
            SUM(CASE WHEN Status='Terminated' THEN 1 ELSE 0 END) AS terminated
        FROM employees
    """)
    snap = run_query("""
        SELECT COUNT(DISTINCT SnapDate) AS snap_weeks, COUNT(*) AS total_rows
        FROM snapshots
    """)
    dept = run_query("""
        SELECT Department, COUNT(*) AS n
        FROM employees
        WHERE Status = 'Active'
        GROUP BY Department
        ORDER BY n DESC
    """)
    return emp, snap, dept


@st.cache_data
def load_data(start_date: str, end_date: str):
    # Weekly active headcount
    hc = run_query(f"""
        SELECT SnapDate, COUNT(*) AS active_hc
        FROM snapshots
        WHERE Status = 'Active'
          AND SnapDate BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY SnapDate ORDER BY SnapDate
    """)
    hc['SnapDate'] = pd.to_datetime(hc['SnapDate'])

    # Weekly active headcount by department — resampled to monthly
    hc_dept = run_query(f"""
        SELECT SnapDate, Department, COUNT(*) AS n
        FROM snapshots
        WHERE Status = 'Active'
          AND SnapDate BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY SnapDate, Department
        ORDER BY SnapDate
    """)
    hc_dept['SnapDate'] = pd.to_datetime(hc_dept['SnapDate'])
    hc_dept_monthly = (
        hc_dept.pivot(index='SnapDate', columns='Department', values='n')
        .resample('ME').last()
        .reset_index()
        .melt(id_vars='SnapDate', var_name='Department', value_name='n')
        .dropna()
    )

    # Monthly new hires
    hires = run_query(f"""
        SELECT strftime('%Y-%m', HireDate) AS month, COUNT(*) AS new_hires
        FROM employees
        WHERE DATE(HireDate) BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY month ORDER BY month
    """)

    # Monthly terminations by type
    terms = run_query(f"""
        SELECT strftime('%Y-%m', TerminationDate) AS month,
               ResignationType, COUNT(*) AS n
        FROM employees
        WHERE TerminationDate IS NOT NULL
          AND DATE(TerminationDate) BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY month, ResignationType
        ORDER BY month
    """)

    return hc, hc_dept_monthly, hires, terms


emp, snap, dept = load_overview()
hc, hc_dept_monthly, hires, terms = load_data(start_date, end_date)

# ── Key metrics ───────────────────────────────────────────────────────────────
st.caption("Dataset totals — reflect the full simulation history and do not change with the sidebar date filter.")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Currently Active",          f"{int(emp['active'][0]):,}")
c2.metric("Terminated",                f"{int(emp['terminated'][0]):,}")
c3.metric("Total Employees (All Time)", f"{int(emp['total_ever'][0]):,}")
c4.metric("Weekly Snapshots",          f"{int(snap['snap_weeks'][0]):,}")
c5.metric("Snapshot Rows",             f"{int(snap['total_rows'][0]) / 1e6:.2f}M")

# ── Active headcount by department ────────────────────────────────────────────
fig_dept = px.bar(
    dept.sort_values('n', ascending=False),
    x='n', y='Department', orientation='h',
    color='Department', color_discrete_map=DEPT_COLORS,
    labels={'n': 'Active Employees', 'Department': ''},
)
fig_dept.update_layout(
    showlegend=False,
    height=320,
    margin=dict(l=0, r=20, t=20, b=20),
)
fig_dept.update_traces(texttemplate='%{x:,}', textposition='outside')
st.plotly_chart(fig_dept, use_container_width=True)

st.divider()

# ── Chart 1: Active headcount over time ──────────────────────────────────────
st.subheader("Active Headcount Over Time")
fig1 = px.line(hc, x='SnapDate', y='active_hc',
               labels={'SnapDate': '', 'active_hc': 'Active Employees'})
fig1.update_traces(line_color='#636EFA')
fig1.update_layout(hovermode='x unified')
st.plotly_chart(fig1, use_container_width=True)

# ── Chart 2: Headcount by department (stacked area, monthly) ─────────────────
st.subheader("Active Headcount by Department (Monthly)")
fig2 = px.area(
    hc_dept_monthly, x='SnapDate', y='n', color='Department',
    color_discrete_map=DEPT_COLORS,
    labels={'SnapDate': '', 'n': 'Active Employees', 'Department': 'Dept'},
)
fig2.update_layout(hovermode='x unified', legend=dict(orientation='h', y=-0.2))
st.plotly_chart(fig2, use_container_width=True)

# ── Chart 3: Monthly new hires vs terminations ────────────────────────────────
st.subheader("Monthly New Hires vs. Terminations")

terms_pivot = (
    terms.pivot_table(index='month', columns='ResignationType', values='n', aggfunc='sum')
    .reset_index()
    .fillna(0)
)
flow = hires.merge(terms_pivot, on='month', how='outer').fillna(0)
flow['month'] = pd.to_datetime(flow['month'] + '-01')
flow = flow.sort_values('month')

col1, col2 = st.columns(2)

with col1:
    fig3a = px.bar(
        flow, x='month', y='new_hires',
        labels={'month': '', 'new_hires': 'New Hires'},
        title='New Hires per Month',
        color_discrete_sequence=['#636EFA'],
    )
    st.plotly_chart(fig3a, use_container_width=True)

with col2:
    term_cols = [c for c in ['Voluntary', 'Involuntary', 'Layoff'] if c in flow.columns]
    term_long = flow.melt(id_vars='month', value_vars=term_cols,
                          var_name='Type', value_name='n')
    fig3b = px.bar(
        term_long, x='month', y='n', color='Type',
        labels={'month': '', 'n': 'Terminations', 'Type': ''},
        title='Terminations per Month',
        color_discrete_map={'Voluntary': '#00CC96', 'Involuntary': '#FFA15A', 'Layoff': '#EF553B'},
        barmode='stack',
    )
    st.plotly_chart(fig3b, use_container_width=True)
