import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
from db import run_query, DEPT_COLORS, RATING_ORDER
from filters import render_sidebar_filter

st.set_page_config(page_title="Engagement & Performance", page_icon="💬", layout="wide")
st.title("💬 Engagement & Performance")

start_date, end_date = render_sidebar_filter()

# Red → yellow → green, one color per rating tier (worst → best)
RATING_COLORS = {
    'Below Expectations':     '#d62728',
    'Inconsistent Performer': '#ff7f0e',
    'Meets Expectations':     '#ffd700',
    'High Performer':         '#2ca02c',
    'Exceeds Expectations':   '#006400',
}


@st.cache_data
def load_data(start_date: str, end_date: str):
    as_of = f"(SELECT MAX(SnapDate) FROM snapshots WHERE SnapDate <= '{end_date}')"

    # Engagement score distribution across all snapshots in the period
    eng_dist = run_query(f"""
        SELECT EngagementIndex FROM snapshots
        WHERE EngagementIndex IS NOT NULL
          AND SnapDate BETWEEN '{start_date}' AND '{end_date}'
    """)

    # Weekly mean engagement over time
    eng_time = run_query(f"""
        SELECT SnapDate, AVG(EngagementIndex) AS mean_eng
        FROM snapshots
        WHERE EngagementIndex IS NOT NULL
          AND Status = 'Active'
          AND SnapDate BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY SnapDate ORDER BY SnapDate
    """)
    eng_time['SnapDate'] = pd.to_datetime(eng_time['SnapDate'])

    # Mean engagement by department, as of end of period
    eng_dept = run_query(f"""
        SELECT Department,
               AVG(EngagementIndex) AS mean_eng,
               COUNT(*) AS n
        FROM snapshots
        WHERE SnapDate = {as_of}
          AND Status = 'Active'
          AND EngagementIndex IS NOT NULL
        GROUP BY Department
        ORDER BY mean_eng DESC
    """)

    # Performance rating distribution — from March review snapshots within the
    # date range. Ratings are only populated in the first week of March each
    # year, so we pull from all March review weeks that fall in the period.
    ratings = run_query(f"""
        SELECT s.PerformanceRating, COUNT(*) AS n
        FROM snapshots s
        WHERE s.PerformanceRating IS NOT NULL
          AND s.Status = 'Active'
          AND s.SnapDate BETWEEN '{start_date}' AND '{end_date}'
          AND s.SnapDate IN (
              SELECT SnapDate FROM snapshots
              WHERE PerformanceRating IS NOT NULL
              GROUP BY SnapDate
              HAVING COUNT(*) > 100
          )
        GROUP BY s.PerformanceRating
    """)

    # Mean engagement by performance rating — same March review snapshots
    rating_eng = run_query(f"""
        SELECT s.PerformanceRating,
               AVG(s.EngagementIndex) AS mean_eng,
               COUNT(*) AS n
        FROM snapshots s
        WHERE s.PerformanceRating IS NOT NULL
          AND s.EngagementIndex IS NOT NULL
          AND s.Status = 'Active'
          AND s.SnapDate BETWEEN '{start_date}' AND '{end_date}'
          AND s.SnapDate IN (
              SELECT SnapDate FROM snapshots
              WHERE PerformanceRating IS NOT NULL
              GROUP BY SnapDate
              HAVING COUNT(*) > 100
          )
        GROUP BY s.PerformanceRating
    """)

    # Rating distribution by year (for trend view)
    ratings_by_year = run_query(f"""
        SELECT strftime('%Y', s.SnapDate) AS Year,
               s.PerformanceRating,
               COUNT(*) AS n
        FROM snapshots s
        WHERE s.PerformanceRating IS NOT NULL
          AND s.Status = 'Active'
          AND s.SnapDate BETWEEN '{start_date}' AND '{end_date}'
          AND s.SnapDate IN (
              SELECT SnapDate FROM snapshots
              WHERE PerformanceRating IS NOT NULL
              GROUP BY SnapDate
              HAVING COUNT(*) > 100
          )
        GROUP BY Year, s.PerformanceRating
    """)

    # RIF events within the period
    rif_df = run_query(f"""
        SELECT SnapDate, COUNT(*) AS layoffs
        FROM snapshots
        WHERE ResignationType = 'Layoff'
          AND SnapDate BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY SnapDate
        HAVING COUNT(*) > 50
        ORDER BY SnapDate
    """)
    rif_df['SnapDate'] = pd.to_datetime(rif_df['SnapDate'])
    rif_dates = rif_df['SnapDate'].tolist()

    return eng_dist, eng_time, eng_dept, ratings, rating_eng, ratings_by_year, rif_dates


eng_dist, eng_time, eng_dept, ratings, rating_eng, ratings_by_year, rif_dates = load_data(start_date, end_date)

# ── Key metrics ───────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Mean Engagement (period)", f"{eng_dist['EngagementIndex'].mean():.1f}")
c2.metric("Std Dev",                   f"{eng_dist['EngagementIndex'].std():.1f}")
c3.metric("Min",                       f"{int(eng_dist['EngagementIndex'].min())}")
c4.metric("Max",                       f"{int(eng_dist['EngagementIndex'].max())}")

st.divider()

# ── Chart 1: Engagement score distribution ───────────────────────────────────
st.subheader("Engagement Score Distribution")
fig1 = px.histogram(
    eng_dist, x='EngagementIndex', nbins=60,
    labels={'EngagementIndex': 'Engagement Score', 'count': 'Snapshot Count'},
    color_discrete_sequence=['#636EFA'],
)
fig1.update_layout(bargap=0.02)
st.plotly_chart(fig1, use_container_width=True)

# ── Chart 2: Mean engagement over time with RIF markers ──────────────────────
st.subheader("Mean Engagement Over Time")
monthly_eng = (
    eng_time.set_index('SnapDate')['mean_eng']
    .resample('ME').mean()
    .reset_index()
)
fig2 = px.line(
    monthly_eng, x='SnapDate', y='mean_eng',
    labels={'SnapDate': '', 'mean_eng': 'Mean Engagement Score'},
)
fig2.update_traces(line_color='#636EFA')
for rif_dt in rif_dates:
    fig2.add_vline(x=rif_dt.isoformat(), line_dash='dash', line_color='red', opacity=0.6)
fig2.update_layout(hovermode='x unified')
st.plotly_chart(fig2, use_container_width=True)

# ── Chart 3: Mean engagement by department ────────────────────────────────────
st.subheader(f"Mean Engagement by Department (as of {end_date})")
fig3 = px.bar(
    eng_dept.sort_values('mean_eng', ascending=True),
    x='mean_eng', y='Department', orientation='h',
    labels={'mean_eng': 'Mean Engagement', 'Department': ''},
    color='Department', color_discrete_map=DEPT_COLORS,
    text='mean_eng',
)
fig3.update_traces(texttemplate='%{text:.1f}', textposition='outside')
fig3.update_layout(showlegend=False, xaxis_range=[60, 85])
st.plotly_chart(fig3, use_container_width=True)

st.divider()

# ── Performance rating section ────────────────────────────────────────────────
st.header("Performance Ratings")
st.caption(
    "Ratings are assigned once per year during the March review cycle. "
    "Charts below reflect all March review snapshots within the selected date range."
)

if ratings.empty:
    st.warning("No performance rating data in the selected date range. "
               "Ensure the range includes at least one March.")
else:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Rating Distribution")
        ratings['PerformanceRating'] = pd.Categorical(
            ratings['PerformanceRating'], categories=RATING_ORDER, ordered=True
        )
        ratings_sorted = ratings.sort_values('PerformanceRating')
        fig4 = px.bar(
            ratings_sorted, x='PerformanceRating', y='n',
            labels={'PerformanceRating': '', 'n': 'Employees'},
            color='PerformanceRating',
            color_discrete_map=RATING_COLORS,
            text='n',
        )
        fig4.update_traces(textposition='outside')
        fig4.update_layout(showlegend=False, xaxis={'tickangle': -20})
        st.plotly_chart(fig4, use_container_width=True)

    with col2:
        st.subheader("Mean Engagement by Rating")
        rating_eng['PerformanceRating'] = pd.Categorical(
            rating_eng['PerformanceRating'], categories=RATING_ORDER, ordered=True
        )
        rating_eng_sorted = rating_eng.sort_values('PerformanceRating')
        fig5 = px.bar(
            rating_eng_sorted, x='PerformanceRating', y='mean_eng',
            labels={'PerformanceRating': '', 'mean_eng': 'Mean Engagement Score'},
            color='PerformanceRating',
            color_discrete_map=RATING_COLORS,
            text='mean_eng',
        )
        fig5.update_traces(texttemplate='%{text:.1f}', textposition='outside')
        fig5.update_layout(showlegend=False, yaxis_range=[60, 85], xaxis={'tickangle': -20})
        st.plotly_chart(fig5, use_container_width=True)

    # ── Chart 6: Rating distribution over time ────────────────────────────────
    if not ratings_by_year.empty:
        st.subheader("Rating Distribution by Year")
        ratings_by_year['PerformanceRating'] = pd.Categorical(
            ratings_by_year['PerformanceRating'], categories=RATING_ORDER, ordered=True
        )
        # Compute % within each year
        year_totals = ratings_by_year.groupby('Year')['n'].transform('sum')
        ratings_by_year['pct'] = (ratings_by_year['n'] / year_totals * 100).round(1)

        fig6 = px.bar(
            ratings_by_year.sort_values(['Year', 'PerformanceRating']),
            x='Year', y='pct',
            color='PerformanceRating',
            color_discrete_map=RATING_COLORS,
            category_orders={'PerformanceRating': RATING_ORDER},
            labels={'pct': '% of Rated Employees', 'Year': '', 'PerformanceRating': 'Rating'},
            barmode='stack',
            text='pct',
        )
        fig6.update_traces(texttemplate='%{text:.0f}%', textposition='inside')
        fig6.update_layout(
            legend=dict(orientation='h', y=-0.15, title=None),
            xaxis=dict(dtick=1),
        )
        st.plotly_chart(fig6, use_container_width=True)
        st.caption("Percentage of rated employees in each tier per March review cycle.")
