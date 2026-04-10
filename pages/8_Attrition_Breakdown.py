import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
from db import run_query, DEPT_COLORS, VOL_COLOR, INVOL_COLOR, LAYOFF_COLOR

st.title("Attrition Breakdown by Department")

RESIGN_COLORS = {
    'Voluntary':   VOL_COLOR,
    'Involuntary': INVOL_COLOR,
    'Layoff':      LAYOFF_COLOR,
}

RESIGN_ORDER = ['Voluntary', 'Involuntary', 'Layoff']


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

    by_type = terms.merge(hc, on=['Year', 'Department'])
    by_type['AttritionPct'] = (by_type['Terminations'] / by_type['AvgHC'] * 100).round(1)
    by_type['AvgHC'] = by_type['AvgHC'].round(0).astype(int)
    return by_type


df = load_attrition_data()

# Exclude types not in our order (shouldn't happen, but safe)
df = df[df['ResignationType'].isin(RESIGN_ORDER)]

depts = sorted(df['Department'].unique())

# ── Chart 1: Stacked bar — faceted by department (3-col grid) ────────────────
st.subheader("Annual Attrition Rate by Type")

fig = px.bar(
    df.sort_values(['Department', 'Year']),
    x='Year', y='AttritionPct',
    color='ResignationType',
    facet_col='Department',
    facet_col_wrap=3,
    labels={'AttritionPct': 'Attrition %', 'Year': '', 'ResignationType': 'Type'},
    color_discrete_map=RESIGN_COLORS,
    category_orders={'ResignationType': RESIGN_ORDER},
    barmode='stack',
    height=700,
)
fig.update_layout(
    legend=dict(orientation='h', y=-0.05, title=None),
    bargap=0.15,
)
fig.for_each_annotation(lambda a: a.update(text=a.text.split('=')[-1]))
fig.update_xaxes(dtick=2, tickangle=-45)
fig.update_yaxes(matches=None, showticklabels=True)
st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Each panel shows one department. Bars are stacked: blue = voluntary, "
    "red = involuntary, orange = layoff (RIF). Y-axes are independent per department "
    "so smaller departments aren't flattened."
)

st.divider()

# ── Chart 2: Line chart — voluntary attrition trend by department ────────────
st.subheader("Voluntary Attrition Trend by Department")

vol_df = df[df['ResignationType'] == 'Voluntary'].copy()

fig2 = px.line(
    vol_df.sort_values(['Department', 'Year']),
    x='Year', y='AttritionPct',
    color='Department',
    color_discrete_map=DEPT_COLORS,
    labels={'AttritionPct': 'Vol. Attrition %', 'Year': ''},
    markers=True,
)
fig2.update_layout(
    hovermode='x unified',
    legend=dict(orientation='h', y=-0.15, title=None),
    height=450,
)
fig2.update_xaxes(dtick=1)
st.plotly_chart(fig2, use_container_width=True)

st.caption(
    "Voluntary attrition is the component most influenced by management quality, "
    "engagement, and compensation. Layoff spikes are excluded here to show the "
    "underlying organic trend."
)
