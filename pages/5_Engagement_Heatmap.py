import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
from db import run_query, SIMIANT_DIVERGING

st.title("Annual Engagement Heatmap")


@st.cache_data
def load_engagement_data():
    """Annual mean engagement by year × department."""
    df = run_query("""
        SELECT strftime('%Y', SnapDate) AS Year,
               Department,
               AVG(EngagementIndex)      AS MeanEngagement,
               COUNT(*)                  AS Observations
        FROM snapshots
        WHERE Status = 'Active'
          AND EngagementIndex IS NOT NULL
        GROUP BY Year, Department
        ORDER BY Year, Department
    """)
    df['MeanEngagement'] = df['MeanEngagement'].round(1)
    return df


df = load_engagement_data()

# Add "All" org-wide row
all_org = df.groupby('Year', as_index=False).agg(
    MeanEngagement=('MeanEngagement', 'mean'),
    Observations=('Observations', 'sum'),
)
all_org['Department'] = 'All'
all_org['MeanEngagement'] = all_org['MeanEngagement'].round(1)
df = pd.concat([df, all_org], ignore_index=True)

# Pivot: rows = Department, columns = Year
pivot = df.pivot(index='Department', columns='Year', values='MeanEngagement').fillna(0)

# Sort departments by overall average engagement (highest at top), keep "All" at top
dept_order = pivot.drop('All', errors='ignore').mean(axis=1).sort_values(ascending=False).index.tolist()
pivot = pivot.loc[['All'] + dept_order]

fig = px.imshow(
    pivot,
    labels=dict(x='Year', y='', color='Mean Eng.'),
    color_continuous_scale=SIMIANT_DIVERGING,
    aspect='auto',
    text_auto='.1f',
)
fig.update_layout(
    height=450,
    xaxis=dict(dtick=1, side='top'),
    coloraxis_colorbar=dict(title='Score'),
)
st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Mean engagement score by year and department. Green = higher engagement, "
    "red = lower. Based on all active-employee snapshots with a non-null "
    "engagement score in each year."
)

st.divider()

# ── Bonus: sparkline table — engagement trend per department ─────────────────
st.subheader("Engagement Trend by Department")

fig2 = px.line(
    df.sort_values(['Department', 'Year']),
    x='Year', y='MeanEngagement',
    color='Department',
    markers=True,
    labels={'MeanEngagement': 'Mean Engagement', 'Year': ''},
)
fig2.update_layout(
    hovermode='x unified',
    legend=dict(orientation='h', y=-0.15, title=None),
    height=400,
)
fig2.update_xaxes(dtick=1)
st.plotly_chart(fig2, use_container_width=True)
