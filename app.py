import streamlit as st
from pathlib import Path
from PIL import Image
import plotly.express as px
from db import run_query, DEPT_COLORS

favicon = Image.open(Path(__file__).parent / "favicon_v1.png")

st.set_page_config(
    page_title="Workforce Analytics",
    page_icon=favicon,
    layout="wide",
)

st.markdown("<style>footer {visibility: hidden;}</style>", unsafe_allow_html=True)
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
            MIN(SnapDate)            AS start_date,
            MAX(SnapDate)            AS end_date,
            COUNT(DISTINCT SnapDate) AS snap_weeks,
            COUNT(*)                 AS total_rows
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

# ── Key metrics ───────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Currently Active",         f"{int(emp['active'][0]):,}")
c2.metric("Terminated",               f"{int(emp['terminated'][0]):,}")
c3.metric("Total Employees (All Time)", f"{int(emp['total_ever'][0]):,}")
c4.metric("Weekly Snapshots",         f"{int(snap['snap_weeks'][0]):,}")
c5.metric("Snapshot Rows",            f"{int(snap['total_rows'][0]) / 1e6:.2f}M")

# ── Active headcount by department (horizontal bar) ───────────────────────────
fig_dept = px.bar(
    dept.sort_values('n', ascending=True),
    x='n', y='Department', orientation='h',
    color='Department', color_discrete_map=DEPT_COLORS,
    labels={'n': 'Active Employees', 'Department': ''},
)
fig_dept.update_layout(
    showlegend=False,
    height=320,
    margin=dict(l=0, r=20, t=20, b=20),
    xaxis=dict(showgrid=True),
)
fig_dept.update_traces(texttemplate='%{x:,}', textposition='outside')
st.plotly_chart(fig_dept, use_container_width=True)

st.divider()

# ── Page directory ────────────────────────────────────────────────────────────
st.markdown(f"**Dataset range:** {snap['start_date'][0]}  →  {snap['end_date'][0]}")

PAGES = [
    ("pages/1_Headcount.py",              "📈 Headcount",
     "Weekly active headcount trend, monthly dept composition as stacked area, "
     "side-by-side monthly new hires vs. terminations by type, and a dept-level HC summary table."),
    ("pages/2_Demographics.py",           "🌍 Demographics",
     "Current-state pie charts for gender, race/ethnicity, and location. "
     "Male/female % trend over time, race by department, and gender by job band — all as % bars."),
    ("pages/3_Org_Health.py",             "🏢 Org Health",
     "Span of control histogram, org layer depth by department, and manager % trend with 10%/25% benchmarks. "
     "Whole-org and per-department centered pyramids showing IC vs. manager split by layer."),
    ("pages/4_Engagement_Performance.py", "💬 Engagement & Performance",
     "Engagement score distribution, mean trend with RIF event markers, and mean by department. "
     "Performance rating distribution, mean engagement by rating tier, and rating mix by year — "
     "all sourced from the annual March review cycle."),
    ("pages/5_Engagement_Heatmap.py",     "💡 Engagement Heatmap",
     "Year × department heatmap of mean engagement scores (red→green). "
     "Org-wide 'All' row at top, departments sorted by average score. "
     "Trend sparklines per department below. Covers full dataset — no date filter."),
    ("pages/6_Attrition.py",              "📉 Attrition",
     "Trailing twelve-month organic attrition rate (vol/invol stacked area) with RIF markers. "
     "Monthly termination counts by type, and annualized attrition bars broken out three ways: "
     "by department, by tenure band, and by performance rating."),
    ("pages/7_Attrition_Heatmap.py",      "🗺️ Attrition Heatmap",
     "Year × department attrition heatmap with a radio toggle for All / Voluntary / Involuntary / Layoff. "
     "Org-wide 'All' row at top, departments sorted by highest average attrition. Covers full dataset."),
    ("pages/8_Attrition_Breakdown.py",    "📊 Attrition Breakdown",
     "Annual attrition stacked bars (vol/invol/layoff) faceted by department in a 3-column grid "
     "with independent y-axes. Voluntary attrition trend lines for all departments overlaid."),
    ("pages/9__Promotions.py",            "🚀 Promotions & Moves",
     "Promotions detected via job band increases: Sankey flow by band, promotions by department, "
     "quarterly trend, IC→manager conversions, and a promotion paths table. "
     "Cross-department move events: top source→destination pairs, quarterly trend, and net flow by department."),
    ("pages/10_Employee_Explorer.py",     "🔍 Employee Explorer",
     "Full employee roster with sidebar filters for status, department, job band, manager flag, "
     "rating, gender, location, engagement range, and resignation type. "
     "Text search by name or ID. Shows manager quality tag and final-state attributes."),
]

for path, label, desc in PAGES:
    c_link, c_desc = st.columns([2, 5])
    with c_link:
        st.page_link(path, label=label)
    with c_desc:
        st.markdown(f"<small>{desc}</small>", unsafe_allow_html=True)

st.divider()

# ── About ─────────────────────────────────────────────────────────────────────
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
""")
