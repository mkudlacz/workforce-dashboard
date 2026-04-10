import streamlit as st
from pathlib import Path
from PIL import Image
from db import run_query

favicon = Image.open(Path(__file__).parent / "favicon_v1.png")

st.set_page_config(
    page_title="Simiant — Workforce Analytics",
    page_icon=favicon,
    layout="wide",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body { font-family: 'Inter', sans-serif !important; }
p, li, td, th, label, input, textarea, select, button,
.stMarkdown, .stText, .stDataFrame, .stCaption,
[data-testid="stSidebar"] a, [data-testid="stSidebar"] p {
    font-family: 'Inter', sans-serif !important;
}
h1, h2, h3, h4, h5, h6 {
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
}
footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


def home():
    st.title("Simiant — Workforce Analytics")
    st.markdown(
        "Explore simulated employee records spanning 11 years for a fictional tech company — "
        "weekly snapshots from 2015 through early 2026. Use the sidebar to navigate."
    )
    st.divider()

    @st.cache_data
    def get_summary():
        return run_query("""
            SELECT MIN(SnapDate) AS start_date, MAX(SnapDate) AS end_date
            FROM snapshots
        """)

    snap = get_summary()
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

Layered on top: three RIF events, drawn from real historical windows — COVID, the 2022 rate
shock, and the 2023 peak tech layoffs. Each one triggers a hiring freeze, an engagement shock,
and a slow recovery that you can see in the data.

Manager quality is baked in at hire — each manager is tagged as poor, star, or neutral, and that
tag quietly shapes the engagement scores and attrition rates of everyone in their reporting chain,
up to two levels deep, for as long as they're here. Engineering and Operations got the best
management cultures. Sales got the worst.

The result is a dataset with real texture: seasonal patterns, RIF fingerprints, engagement
divergence by department, tenure effects on attrition. It behaves the way workforce data
actually behaves — which makes it genuinely useful for building and testing analytics.
""")


pg = st.navigation(
    {
        "Overview": [
            st.Page(home, title="Home", icon=None, default=True),
            st.Page("pages/1_Headcount.py",              title="Headcount"),
            st.Page("pages/2_Demographics.py",            title="Demographics"),
            st.Page("pages/3_Org_Health.py",              title="Org Health"),
            st.Page("pages/10_Employee_Explorer.py",      title="Employee Explorer"),
        ],
        "Engagement & Performance": [
            st.Page("pages/4_Engagement_Performance.py",  title="Engagement & Performance"),
            st.Page("pages/5_Engagement_Heatmap.py",      title="Engagement Heatmap"),
        ],
        "Attrition": [
            st.Page("pages/6_Attrition.py",               title="Attrition"),
            st.Page("pages/7_Attrition_Heatmap.py",       title="Attrition Heatmap"),
            st.Page("pages/8_Attrition_Breakdown.py",     title="Attrition Breakdown"),
            st.Page("pages/11_Attrition_Seasonality.py",  title="Attrition Seasonality"),
        ],
        "Workforce Dynamics": [
            st.Page("pages/12_Macro_Shocks.py",           title="Macro Shocks & Survivor Syndrome"),
            st.Page("pages/13_Tenure_Hazard.py",          title="Tenure Hazard Profile"),
            st.Page("pages/14_Performance_Attrition.py",  title="Performance & Attrition"),
            st.Page("pages/15_Manager_Quality.py",        title="Manager Quality"),
            st.Page("pages/16_Manager_Cascades.py",       title="Manager Departure Cascades"),
            st.Page("pages/17_Engagement_Signal.py",      title="Engagement as Attrition Signal"),
            st.Page("pages/18_RIF_Targeting.py",          title="RIF Targeting Patterns"),
            st.Page("pages/19_Org_Shape.py",              title="Org Shape Over Time"),
        ],
        "Mobility": [
            st.Page("pages/9__Promotions.py",             title="Promotions & Moves"),
        ],
    }
)

pg.run()
