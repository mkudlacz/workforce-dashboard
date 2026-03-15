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

    # Dept-level HC summary: active HC + hires/terms by type in period
    dept_summary = run_query(f"""
        SELECT
            e.Department,
            SUM(CASE WHEN DATE(e.HireDate) BETWEEN '{start_date}' AND '{end_date}'
                     THEN 1 ELSE 0 END)                                              AS Hires,
            SUM(CASE WHEN e.ResignationType = 'Voluntary'
                      AND DATE(e.TerminationDate) BETWEEN '{start_date}' AND '{end_date}'
                     THEN 1 ELSE 0 END)                                              AS VolTerms,
            SUM(CASE WHEN e.ResignationType = 'Involuntary'
                      AND DATE(e.TerminationDate) BETWEEN '{start_date}' AND '{end_date}'
                     THEN 1 ELSE 0 END)                                              AS InvolTerms,
            SUM(CASE WHEN e.ResignationType = 'Layoff'
                      AND DATE(e.TerminationDate) BETWEEN '{start_date}' AND '{end_date}'
                     THEN 1 ELSE 0 END)                                              AS Layoffs
        FROM employees e
        GROUP BY e.Department
    """)
    as_of = f"(SELECT MAX(SnapDate) FROM snapshots WHERE SnapDate <= '{end_date}')"
    active_by_dept = run_query(f"""
        SELECT Department, COUNT(*) AS ActiveHC
        FROM snapshots
        WHERE SnapDate = {as_of} AND Status = 'Active'
        GROUP BY Department
    """)
    dept_summary = (
        active_by_dept
        .merge(dept_summary, on='Department', how='left')
        .fillna(0)
    )
    dept_summary['Net'] = (
        dept_summary['Hires']
        - dept_summary['VolTerms']
        - dept_summary['InvolTerms']
        - dept_summary['Layoffs']
    ).astype(int)
    for col in ['Hires', 'VolTerms', 'InvolTerms', 'Layoffs']:
        dept_summary[col] = dept_summary[col].astype(int)
    dept_summary = dept_summary.sort_values('ActiveHC', ascending=False)

    return hc, hc_dept_monthly, hires, terms, dept_summary


hc, hc_dept_monthly, hires, terms, dept_summary = load_data(start_date, end_date)

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

# ── Dept HC summary table ─────────────────────────────────────────────────────
st.subheader(f"Headcount Summary by Department (as of {end_date})")
st.dataframe(
    dept_summary.rename(columns={
        'Department': 'Department',
        'ActiveHC':   'Active HC',
        'Hires':      'Hires',
        'VolTerms':   'Vol Terms',
        'InvolTerms': 'Invol Terms',
        'Layoffs':    'Layoffs',
        'Net':        'Net (Hires − Terms)',
    }),
    hide_index=True,
    use_container_width=True,
)
st.caption(
    "Hires and terminations reflect the selected date range. Active HC is point-in-time as of "
    "the period end date. Net does not account for cross-department moves — see Promotions & Moves for transfer detail."
)
