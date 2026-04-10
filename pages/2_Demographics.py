import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
from db import run_query, DEPT_COLORS, GENDER_COLORS
from filters import render_sidebar_filter

st.title("Demographics")

start_date, end_date = render_sidebar_filter()


@st.cache_data
def load_data(start_date: str, end_date: str):
    as_of = f"(SELECT MAX(SnapDate) FROM snapshots WHERE SnapDate <= '{end_date}')"

    # Current active breakdowns — as of end of selected period
    gender = run_query(f"""
        SELECT e.Gender, COUNT(*) AS n
        FROM snapshots s JOIN employees e ON s.EmployeeID = e.EmployeeID
        WHERE s.SnapDate = {as_of} AND s.Status = 'Active'
        GROUP BY e.Gender ORDER BY n DESC
    """)
    race = run_query(f"""
        SELECT e.RaceEthnicity, COUNT(*) AS n
        FROM snapshots s JOIN employees e ON s.EmployeeID = e.EmployeeID
        WHERE s.SnapDate = {as_of} AND s.Status = 'Active'
        GROUP BY e.RaceEthnicity ORDER BY n DESC
    """)
    location = run_query(f"""
        SELECT e.Location, COUNT(*) AS n
        FROM snapshots s JOIN employees e ON s.EmployeeID = e.EmployeeID
        WHERE s.SnapDate = {as_of} AND s.Status = 'Active'
        GROUP BY e.Location ORDER BY n DESC
    """)

    # Gender % over time (monthly, Male/Female only)
    gender_time = run_query(f"""
        SELECT s.SnapDate, e.Gender, COUNT(*) AS n
        FROM snapshots s
        JOIN employees e ON s.EmployeeID = e.EmployeeID
        WHERE s.Status = 'Active'
          AND e.Gender IN ('Male', 'Female')
          AND s.SnapDate BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY s.SnapDate, e.Gender
        ORDER BY s.SnapDate
    """)
    gender_time['SnapDate'] = pd.to_datetime(gender_time['SnapDate'])

    # Race/ethnicity by department, as of end of period
    race_dept = run_query(f"""
        SELECT s.Department, e.RaceEthnicity, COUNT(*) AS n
        FROM snapshots s JOIN employees e ON s.EmployeeID = e.EmployeeID
        WHERE s.SnapDate = {as_of} AND s.Status = 'Active'
        GROUP BY s.Department, e.RaceEthnicity
        ORDER BY s.Department
    """)

    # Gender by job band, as of end of period
    band_gender = run_query(f"""
        SELECT s.JobBand, e.Gender, COUNT(*) AS n
        FROM snapshots s JOIN employees e ON s.EmployeeID = e.EmployeeID
        WHERE s.SnapDate = {as_of}
          AND s.Status = 'Active'
          AND e.Gender IN ('Male', 'Female')
        GROUP BY s.JobBand, e.Gender
        ORDER BY s.JobBand
    """)

    return gender, race, location, gender_time, race_dept, band_gender


gender, race, location, gender_time, race_dept, band_gender = load_data(start_date, end_date)

# ── Chart 1: Current active demographic breakdowns ───────────────────────────
st.subheader(f"Active Workforce Composition (as of {end_date})")
col1, col2, col3 = st.columns(3)

with col1:
    fig1 = px.pie(gender, names='Gender', values='n', title='Gender',
                  color_discrete_sequence=px.colors.qualitative.Pastel)
    fig1.update_traces(textinfo='percent+label')
    st.plotly_chart(fig1, use_container_width=True)

with col2:
    fig2 = px.pie(race, names='RaceEthnicity', values='n', title='Race / Ethnicity',
                  color_discrete_sequence=px.colors.qualitative.Set3)
    fig2.update_traces(textinfo='percent+label')
    st.plotly_chart(fig2, use_container_width=True)

with col3:
    fig3 = px.pie(location, names='Location', values='n', title='Location',
                  color_discrete_sequence=px.colors.qualitative.Pastel1)
    fig3.update_traces(textinfo='percent+label')
    st.plotly_chart(fig3, use_container_width=True)

st.divider()

# ── Chart 2: Male/Female % over time ─────────────────────────────────────────
st.subheader("Male / Female Composition Over Time")
pivot = (
    gender_time.pivot_table(index='SnapDate', columns='Gender', values='n', aggfunc='sum')
    .resample('ME').last()
    .reset_index()
)
pivot['Total']    = pivot['Male'] + pivot['Female']
pivot['Female %'] = pivot['Female'] / pivot['Total'] * 100
pivot['Male %']   = pivot['Male']   / pivot['Total'] * 100
pct_long = pivot.melt(id_vars='SnapDate', value_vars=['Female %', 'Male %'],
                      var_name='Gender', value_name='pct')
fig4 = px.line(
    pct_long, x='SnapDate', y='pct', color='Gender',
    labels={'SnapDate': '', 'pct': '% of Active Workforce', 'Gender': ''},
    color_discrete_map={'Female %': GENDER_COLORS['Female'], 'Male %': GENDER_COLORS['Male']},
)
fig4.add_hline(y=50, line_dash='dot', line_color='grey', opacity=0.5)
fig4.update_layout(hovermode='x unified', yaxis_range=[40, 60])
st.plotly_chart(fig4, use_container_width=True)

# ── Charts 3–4 ────────────────────────────────────────────────────────────────
col4, col5 = st.columns(2)

with col4:
    st.subheader(f"Race / Ethnicity by Department (as of {end_date})")
    total_by_dept    = race_dept.groupby('Department')['n'].sum().rename('total')
    race_dept_pct    = race_dept.merge(total_by_dept, on='Department')
    race_dept_pct['pct'] = race_dept_pct['n'] / race_dept_pct['total'] * 100
    fig5 = px.bar(
        race_dept_pct, x='Department', y='pct', color='RaceEthnicity',
        labels={'pct': '% of Dept', 'Department': '', 'RaceEthnicity': 'Race/Ethnicity'},
        barmode='stack',
    )
    fig5.update_layout(legend=dict(orientation='h', y=-0.3), xaxis={'tickangle': -30})
    st.plotly_chart(fig5, use_container_width=True)

with col5:
    st.subheader(f"Gender by Job Band (as of {end_date})")
    total_by_band = band_gender.groupby('JobBand')['n'].sum().rename('total')
    band_pct      = band_gender.merge(total_by_band, on='JobBand')
    band_pct['pct'] = band_pct['n'] / band_pct['total'] * 100
    band_order = ['IC1', 'IC2', 'IC3', 'M1', 'M2', 'M3', 'VP']
    fig6 = px.bar(
        band_pct, x='JobBand', y='pct', color='Gender',
        labels={'pct': '% of Band', 'JobBand': 'Job Band', 'Gender': ''},
        barmode='stack',
        category_orders={'JobBand': band_order},
        color_discrete_map={'Female': GENDER_COLORS['Female'], 'Male': GENDER_COLORS['Male']},
    )
    fig6.add_hline(y=50, line_dash='dot', line_color='grey', opacity=0.5)
    fig6.update_layout(legend=dict(orientation='h', y=-0.2))
    st.plotly_chart(fig6, use_container_width=True)
