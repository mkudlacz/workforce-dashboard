import streamlit as st
from db import run_query

st.set_page_config(
    page_title="Workforce Analytics",
    page_icon="👥",
    layout="wide",
)

st.title("👥 Workforce Analytics Dashboard")
st.markdown(
    "Explore simulated employee records spanning 11 years for a fictional tech company — "
    "weekly snapshots from 2015 through early 2026. Use the sidebar to navigate."
)
st.divider()


@st.cache_data
def get_summary():
    emp = run_query("""
        SELECT
            COUNT(*)                                              AS total_ever,
            SUM(CASE WHEN Status='Active'     THEN 1 ELSE 0 END) AS active,
            SUM(CASE WHEN Status='Terminated' THEN 1 ELSE 0 END) AS terminated
        FROM employees
    """)
    snap = run_query("""
        SELECT
            MIN(SnapDate)           AS start_date,
            MAX(SnapDate)           AS end_date,
            COUNT(DISTINCT SnapDate) AS snap_weeks,
            COUNT(*)                AS total_rows
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


emp, snap, dept = get_summary()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Employees Ever",  f"{int(emp['total_ever'][0]):,}")
c2.metric("Currently Active",      f"{int(emp['active'][0]):,}")
c3.metric("Terminated",            f"{int(emp['terminated'][0]):,}")
c4.metric("Weekly Snapshots",      f"{int(snap['snap_weeks'][0]):,}")
c5.metric("Snapshot Rows",         f"{int(snap['total_rows'][0]) / 1e6:.2f}M")

st.divider()

col_left, col_right = st.columns([2, 1])

with col_left:
    st.markdown(f"**Dataset range:** {snap['start_date'][0]}  →  {snap['end_date'][0]}")
    st.markdown("""
**About this dataset**

This database models a company that has been operating for ~16 years — the product of a
merger between two organizations. Records begin partway through the company's history,
mimicking an HCM system populated for an existing workforce rather than tracking the
company from its founding.

| Page | What you'll find |
|---|---|
| 📈 Headcount | Workforce size over time, hiring & attrition flows, dept composition |
| 📉 Attrition | Organic vol/invol rates, RIF events, attrition by tenure/rating/dept |
| 🏢 Org Health | Span of control, org layer depth by dept, manager % over time |
| 💬 Engagement & Performance | Engagement trends, RIF shocks, rating distribution, cross-tabs |
| 🌍 Demographics | Gender, race/ethnicity, location — current state and over time |
""")

with col_right:
    st.markdown("**Active headcount by department**")
    st.dataframe(dept.rename(columns={'Department': 'Dept', 'n': 'Active'}), hide_index=True, use_container_width=True)
