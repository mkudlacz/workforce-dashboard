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
c1.metric("Currently Active Employees",      f"{int(emp['active'][0]):,}")
c2.metric("Terminated",            f"{int(emp['terminated'][0]):,}")
c3.metric("Total Employees (All Time)",  f"{int(emp['total_ever'][0]):,}")
c4.metric("Weekly Snapshots",      f"{int(snap['snap_weeks'][0]):,}")
c5.metric("Snapshot Rows",         f"{int(snap['total_rows'][0]) / 1e6:.2f}M")

st.divider()

col_left, col_right = st.columns([2, 1])

with col_left:
    st.markdown(f"**Dataset range:** {snap['start_date'][0]}  →  {snap['end_date'][0]}")
    st.markdown("""
**About this dataset**

This is a fictional mid-size tech company — built from scratch in Python, one week at a time.
The simulation runs from January 2015 through early 2026: ~585 Monday snapshots, each capturing
every active employee's department, role, engagement score, performance rating, manager, and more.

The company starts at around 3,200 employees, grows steadily through 2022 to just over 5,100,
then contracts. That arc isn't hardcoded — it emerges from a target headcount curve with
mean-reverting noise, a hiring function that responds to gaps with realistic lag, and a monthly
recruiting capacity budget that prevents the unrealistic week-to-week spikes real data never shows.

Attrition is where things get interesting. Voluntary and involuntary rates are built from stacked
multipliers: your tenure, your performance rating, your engagement score, your manager's exit
history, and the time of year (March is rough — equity vests, and people leave). Department
multipliers mean Sales churns at 1.5x the baseline; Legal barely moves.

Layered on top: 1–3 RIF events, drawn from four real historical windows — the 2016 growth
correction, COVID, the 2022 rate shock, and the 2023 peak tech layoffs. Each one triggers a
hiring freeze, an engagement shock, and a slow recovery that you can see in the data.

Manager quality is baked in at hire — each manager is tagged as poor, star, or neutral, and that
tag quietly shapes the engagement scores and attrition rates of everyone in their reporting chain,
up to two levels deep, for as long as they're here. Engineering and Operations got the best
management cultures. Sales got the worst.

The result is a dataset with real texture: seasonal patterns, RIF fingerprints, engagement
divergence by department, tenure effects on attrition. It behaves the way workforce data
actually behaves — which makes it genuinely useful for building and testing analytics.

| Page | What you'll find |
|---|---|
| 📈 Headcount | Workforce size over time, hiring & attrition flows, dept composition |
| 🌍 Demographics | Gender, race/ethnicity, location — current state and over time |
| 🏢 Org Health | Span of control, org layers by dept, manager % over time |
| 💬 Engagement & Performance | Engagement trends, RIF shocks, rating distribution, cross-tabs |
| 💡 Engagement Heatmap | Year × department engagement with sparklines |
| 📉 Attrition | Organic vol/invol rates, RIF events, attrition by tenure/rating/dept |
| 🔥 Attrition Heatmap | Year × department view, toggle by termination type |
| 📊 Attrition Breakdown | Annual attrition trends faceted by department |
| 🚀 Promotions & Moves | Band promotions, IC→manager conversions, cross-dept transfers |
| 🔍 Employee Explorer | Filterable employee roster with engagement and rating detail |
""")

with col_right:
    st.markdown("**Active headcount by department**")
    st.dataframe(dept.rename(columns={'Department': 'Dept', 'n': 'Active'}), hide_index=True, use_container_width=True)
