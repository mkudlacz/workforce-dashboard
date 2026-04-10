import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
from db import run_query, DEPT_COLORS, SIMIANT_DIVERGING_R

st.title("Annual Attrition Heatmap")


@st.cache_data
def load_attrition_data():
    """Annual attrition rate by year × department × resignation type."""
    terms = run_query("""
        SELECT strftime('%Y', SnapDate) AS Year,
               Department,
               ResignationType,
               COUNT(*)                 AS Terminations
        FROM snapshots
        WHERE Status = 'Terminated'
        GROUP BY Year, Department, ResignationType
    """)

    hc = run_query("""
        SELECT Year, Department, AVG(weekly_hc) AS AvgHC
        FROM (
            SELECT strftime('%Y', SnapDate) AS Year,
                   Department,
                   SnapDate,
                   COUNT(*)                 AS weekly_hc
            FROM snapshots
            WHERE Status = 'Active'
            GROUP BY SnapDate, Department
        )
        GROUP BY Year, Department
    """)

    # Build per-type rows
    by_type = terms.merge(hc, on=['Year', 'Department'])
    by_type['AttritionPct'] = (by_type['Terminations'] / by_type['AvgHC'] * 100).round(1)

    # Build "All" rollup
    totals = (
        terms.groupby(['Year', 'Department'], as_index=False)['Terminations']
        .sum()
        .merge(hc, on=['Year', 'Department'])
    )
    totals['ResignationType'] = 'All'
    totals['AttritionPct'] = (totals['Terminations'] / totals['AvgHC'] * 100).round(1)

    df = pd.concat([by_type, totals], ignore_index=True)
    df['AvgHC'] = df['AvgHC'].round(0).astype(int)

    # Add "All" org-wide department row for each resignation type
    org_wide = (
        df.groupby(['Year', 'ResignationType'], as_index=False)
        .agg(Terminations=('Terminations', 'sum'), AvgHC=('AvgHC', 'sum'))
    )
    org_wide['Department'] = 'All'
    org_wide['AttritionPct'] = (org_wide['Terminations'] / org_wide['AvgHC'] * 100).round(1)
    df = pd.concat([df, org_wide], ignore_index=True)

    return df


df = load_attrition_data()

# Resignation type selector
type_options = ['All', 'Voluntary', 'Involuntary', 'Layoff']
available = [t for t in type_options if t in df['ResignationType'].unique()]
selected_type = st.radio("Resignation type", available, horizontal=True)

heatmap_df = df[df['ResignationType'] == selected_type].copy()

# Pivot for heatmap: rows = Department, columns = Year
pivot = heatmap_df.pivot(index='Department', columns='Year', values='AttritionPct').fillna(0)

# Sort departments by overall average attrition (highest at top), keep "All" at top
dept_order = pivot.drop('All', errors='ignore').mean(axis=1).sort_values(ascending=False).index.tolist()
pivot = pivot.loc[['All'] + dept_order]

fig = px.imshow(
    pivot,
    labels=dict(x='Year', y='', color='Attrition %'),
    color_continuous_scale=SIMIANT_DIVERGING_R,
    aspect='auto',
    text_auto='.1f',
)
fig.update_layout(
    height=450,
    xaxis=dict(dtick=1, side='top'),
    coloraxis_colorbar=dict(title='%'),
)
st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Attrition % = terminations in the year / average weekly active headcount. "
    "Departments sorted by overall average (highest at top). "
    "Partial years (first and last) may appear lower than actual annualized rate."
)
