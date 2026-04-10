import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from db import run_query, DEPT_COLORS, RATING_ORDER, TENURE_ORDER, VOL_COLOR, INVOL_COLOR, LAYOFF_COLOR, RIF_COLOR
from filters import render_sidebar_filter

st.title("Attrition Analysis")

start_date, end_date = render_sidebar_filter()


@st.cache_data
def load_data(start_date: str, end_date: str):
    # Fetch 52 extra weeks (1 year) before start_date so the TTM window is
    # fully warmed up by the time we reach the visible range.
    lookback_start = (
        datetime.strptime(start_date, '%Y-%m-%d') - timedelta(weeks=52)
    ).strftime('%Y-%m-%d')

    # Weekly active headcount (with lookback)
    hc = run_query(f"""
        SELECT SnapDate, COUNT(*) AS active_hc
        FROM snapshots
        WHERE Status = 'Active'
          AND SnapDate BETWEEN '{lookback_start}' AND '{end_date}'
        GROUP BY SnapDate ORDER BY SnapDate
    """)

    # Weekly organic terminations split by type (with lookback)
    org_terms = run_query(f"""
        SELECT SnapDate, ResignationType, COUNT(*) AS terms
        FROM snapshots
        WHERE Status = 'Terminated'
          AND ResignationType IN ('Voluntary', 'Involuntary')
          AND SnapDate BETWEEN '{lookback_start}' AND '{end_date}'
        GROUP BY SnapDate, ResignationType
        ORDER BY SnapDate
    """)

    # Monthly terminations by type
    monthly_terms = run_query(f"""
        SELECT strftime('%Y-%m', TerminationDate) AS month,
               ResignationType, COUNT(*) AS n
        FROM employees
        WHERE TerminationDate IS NOT NULL
          AND DATE(TerminationDate) BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY month, ResignationType
        ORDER BY month
    """)

    # Annualized organic attrition by department — vol and invol split
    dept_attr = run_query(f"""
        SELECT Department,
               SUM(CASE WHEN Status='Terminated'
                         AND ResignationType='Voluntary'   THEN 1 ELSE 0 END) AS vol_terms,
               SUM(CASE WHEN Status='Terminated'
                         AND ResignationType='Involuntary' THEN 1 ELSE 0 END) AS invol_terms,
               SUM(CASE WHEN Status='Active' THEN 1 ELSE 0 END)               AS active_weeks
        FROM snapshots
        WHERE SnapDate BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY Department
    """)
    dept_attr['vol_pct']   = (dept_attr['vol_terms']   / dept_attr['active_weeks'] * 52 * 100).round(1)
    dept_attr['invol_pct'] = (dept_attr['invol_terms'] / dept_attr['active_weeks'] * 52 * 100).round(1)
    dept_attr['annual_pct'] = (dept_attr['vol_pct'] + dept_attr['invol_pct']).round(1)

    # Attrition by tenure band — vol and invol split
    tenure_attr = run_query(f"""
        SELECT
            CASE
                WHEN TenureYears < 0.5  THEN '< 6 mo'
                WHEN TenureYears < 1.5  THEN '6–18 mo'
                WHEN TenureYears < 3    THEN '1.5–3 yr'
                WHEN TenureYears < 5    THEN '3–5 yr'
                WHEN TenureYears < 8    THEN '5–8 yr'
                ELSE                         '8+ yr'
            END AS tenure_band,
            SUM(CASE WHEN Status='Terminated'
                      AND ResignationType='Voluntary'   THEN 1 ELSE 0 END) AS vol_terms,
            SUM(CASE WHEN Status='Terminated'
                      AND ResignationType='Involuntary' THEN 1 ELSE 0 END) AS invol_terms,
            SUM(CASE WHEN Status='Active' THEN 1 ELSE 0 END)               AS active_weeks
        FROM snapshots
        WHERE SnapDate BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY tenure_band
    """)
    tenure_attr['vol_pct']   = (tenure_attr['vol_terms']   / tenure_attr['active_weeks'] * 52 * 100).round(1)
    tenure_attr['invol_pct'] = (tenure_attr['invol_terms'] / tenure_attr['active_weeks'] * 52 * 100).round(1)
    tenure_attr['annual_pct'] = (tenure_attr['vol_pct'] + tenure_attr['invol_pct']).round(1)

    # Attrition by performance rating — vol and invol split
    # Uses employees.LatestRating so the denominator is all active weeks, not
    # just the one March snapshot per year when ratings are recorded.
    rating_attr = run_query(f"""
        SELECT e.LatestRating AS PerformanceRating,
               SUM(CASE WHEN s.Status='Terminated'
                         AND s.ResignationType='Voluntary'   THEN 1 ELSE 0 END) AS vol_terms,
               SUM(CASE WHEN s.Status='Terminated'
                         AND s.ResignationType='Involuntary' THEN 1 ELSE 0 END) AS invol_terms,
               SUM(CASE WHEN s.Status='Active' THEN 1 ELSE 0 END)               AS active_weeks
        FROM employees e
        JOIN snapshots s ON e.EmployeeID = s.EmployeeID
        WHERE e.LatestRating IS NOT NULL
          AND s.SnapDate BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY e.LatestRating
    """)
    rating_attr['vol_pct']   = (rating_attr['vol_terms']   / rating_attr['active_weeks'] * 52 * 100).round(1)
    rating_attr['invol_pct'] = (rating_attr['invol_terms'] / rating_attr['active_weeks'] * 52 * 100).round(1)
    rating_attr['annual_pct'] = (rating_attr['vol_pct'] + rating_attr['invol_pct']).round(1)

    # RIF events within the selected period
    rif_dates_df = run_query(f"""
        SELECT SnapDate, COUNT(*) AS layoffs
        FROM snapshots
        WHERE ResignationType = 'Layoff'
          AND SnapDate BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY SnapDate
        HAVING COUNT(*) > 50
        ORDER BY SnapDate
    """)
    rif_dates_df['SnapDate'] = pd.to_datetime(rif_dates_df['SnapDate'])
    rif_dates = rif_dates_df['SnapDate'].tolist()

    return hc, org_terms, monthly_terms, dept_attr, tenure_attr, rating_attr, rif_dates


hc, org_terms, monthly_terms, dept_attr, tenure_attr, rating_attr, rif_dates = load_data(start_date, end_date)

# ── Chart 1: Rolling 12-week annualized organic attrition ────────────────────
st.subheader("Trailing Twelve Month (TTM) Organic Attrition Rate — Vol vs. Invol")

# Pivot org_terms to one row per SnapDate with vol and invol columns
terms_pivot = (
    org_terms.pivot_table(index='SnapDate', columns='ResignationType', values='terms', aggfunc='sum')
    .reset_index()
    .rename(columns={'Voluntary': 'vol', 'Involuntary': 'invol'})
)

df = (
    hc.merge(terms_pivot, on='SnapDate', how='left')
    .fillna({'vol': 0, 'invol': 0})
    .assign(SnapDate=lambda d: pd.to_datetime(d['SnapDate']))
    .sort_values('SnapDate')
)
df['rolling_vol']   = df['vol'].rolling(52, min_periods=52).sum()
df['rolling_invol'] = df['invol'].rolling(52, min_periods=52).sum()
df['rolling_hc']    = df['active_hc'].rolling(52, min_periods=52).mean()
# TTM: sum of 52 weekly terms / mean weekly HC — /52 * 52 cancels, leaving * 100
df['vol_rate']      = (df['rolling_vol']   / df['rolling_hc'] * 100).clip(0, 50)
df['invol_rate']    = (df['rolling_invol'] / df['rolling_hc'] * 100).clip(0, 50)

# Trim to selected range — lookback rows were only for warm-up
df = df[df['SnapDate'] >= pd.to_datetime(start_date)]

rate_long = (
    df.dropna(subset=['vol_rate', 'invol_rate'])
    .melt(id_vars='SnapDate', value_vars=['vol_rate', 'invol_rate'],
          var_name='Type', value_name='annual_rate')
)
rate_long['Type'] = rate_long['Type'].map({'vol_rate': 'Voluntary', 'invol_rate': 'Involuntary'})

fig1 = px.area(
    rate_long, x='SnapDate', y='annual_rate', color='Type',
    labels={'SnapDate': '', 'annual_rate': 'Annualized Rate (%)', 'Type': ''},
    color_discrete_map={'Voluntary': VOL_COLOR, 'Involuntary': INVOL_COLOR},
    category_orders={'Type': ['Involuntary', 'Voluntary']},  # Voluntary on bottom
)
for rif_dt in rif_dates:
    fig1.add_vline(x=rif_dt.isoformat(), line_dash='dash', line_color=RIF_COLOR, opacity=0.6)
fig1.update_layout(hovermode='x unified', legend=dict(orientation='h', y=-0.15))
st.plotly_chart(fig1, use_container_width=True)

# ── Chart 2: Monthly terminations by type ─────────────────────────────────────
st.subheader("Monthly Terminations by Type")

monthly_terms['month'] = pd.to_datetime(monthly_terms['month'] + '-01')
fig2 = px.bar(
    monthly_terms.sort_values('month'), x='month', y='n', color='ResignationType',
    labels={'month': '', 'n': 'Terminations', 'ResignationType': 'Type'},
    color_discrete_map={'Voluntary': VOL_COLOR, 'Involuntary': INVOL_COLOR, 'Layoff': LAYOFF_COLOR},
    barmode='stack',
)
for rif_dt in rif_dates:
    fig2.add_vline(x=rif_dt.isoformat(), line_dash='dash', line_color=RIF_COLOR, opacity=0.4)
fig2.update_layout(legend=dict(orientation='h', y=-0.2))
st.plotly_chart(fig2, use_container_width=True)

# ── Charts 3–5 in columns ─────────────────────────────────────────────────────

def add_total_labels_h(fig, df, y_col, total_col):
    """Add total data labels to the right of a horizontal stacked bar chart."""
    for _, row in df.iterrows():
        fig.add_annotation(
            x=row[total_col], y=row[y_col],
            text=f"<b>{row[total_col]:.1f}%</b>",
            xanchor='left', showarrow=False, xshift=6,
            font=dict(size=11),
        )

def add_total_labels_v(fig, df, x_col, total_col):
    """Add total data labels above a vertical stacked bar chart."""
    for _, row in df.iterrows():
        fig.add_annotation(
            x=row[x_col], y=row[total_col],
            text=f"<b>{row[total_col]:.1f}%</b>",
            yanchor='bottom', showarrow=False, yshift=4,
            font=dict(size=11),
        )

VOL_INVOL_COLORS = {'Voluntary': VOL_COLOR, 'Involuntary': INVOL_COLOR}

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("By Department")
    dept_sorted = dept_attr.sort_values('annual_pct', ascending=True)
    dept_long   = dept_sorted.melt(
        id_vars=['Department', 'annual_pct'],
        value_vars=['vol_pct', 'invol_pct'], var_name='Type', value_name='rate'
    )
    dept_long['Type'] = dept_long['Type'].map({'vol_pct': 'Voluntary', 'invol_pct': 'Involuntary'})
    fig3 = px.bar(
        dept_long, x='rate', y='Department', color='Type', orientation='h', barmode='stack',
        labels={'rate': 'Annualized %', 'Department': '', 'Type': ''},
        color_discrete_map=VOL_INVOL_COLORS,
        category_orders={'Type': ['Involuntary', 'Voluntary']},
    )
    add_total_labels_h(fig3, dept_sorted, 'Department', 'annual_pct')
    fig3.update_layout(showlegend=True, legend=dict(orientation='h', y=-0.15),
                       xaxis=dict(title='Annualized %', range=[0, dept_sorted['annual_pct'].max() * 1.25]))
    st.plotly_chart(fig3, use_container_width=True)

with col2:
    st.subheader("By Tenure Band")
    tenure_attr['tenure_band'] = pd.Categorical(
        tenure_attr['tenure_band'], categories=TENURE_ORDER, ordered=True
    )
    tenure_sorted = tenure_attr.sort_values('tenure_band')
    tenure_long   = tenure_sorted.melt(
        id_vars=['tenure_band', 'annual_pct'],
        value_vars=['vol_pct', 'invol_pct'], var_name='Type', value_name='rate'
    )
    tenure_long['Type'] = tenure_long['Type'].map({'vol_pct': 'Voluntary', 'invol_pct': 'Involuntary'})
    fig4 = px.bar(
        tenure_long, x='tenure_band', y='rate', color='Type', barmode='stack',
        labels={'rate': 'Annualized %', 'tenure_band': 'Tenure', 'Type': ''},
        color_discrete_map=VOL_INVOL_COLORS,
        category_orders={'Type': ['Involuntary', 'Voluntary']},
    )
    add_total_labels_v(fig4, tenure_sorted, 'tenure_band', 'annual_pct')
    fig4.update_layout(showlegend=True, legend=dict(orientation='h', y=-0.15),
                       yaxis=dict(title='Annualized %', range=[0, tenure_sorted['annual_pct'].max() * 1.25]))
    st.plotly_chart(fig4, use_container_width=True)

with col3:
    st.subheader("By Performance Rating")
    rating_attr['PerformanceRating'] = pd.Categorical(
        rating_attr['PerformanceRating'], categories=RATING_ORDER, ordered=True
    )
    rating_sorted = rating_attr.sort_values('PerformanceRating')
    rating_long   = rating_sorted.melt(
        id_vars=['PerformanceRating', 'annual_pct'],
        value_vars=['vol_pct', 'invol_pct'], var_name='Type', value_name='rate'
    )
    rating_long['Type'] = rating_long['Type'].map({'vol_pct': 'Voluntary', 'invol_pct': 'Involuntary'})
    fig5 = px.bar(
        rating_long, x='rate', y='PerformanceRating', color='Type', orientation='h', barmode='stack',
        labels={'rate': 'Annualized %', 'PerformanceRating': '', 'Type': ''},
        color_discrete_map=VOL_INVOL_COLORS,
        category_orders={
            'Type': ['Involuntary', 'Voluntary'],
            'PerformanceRating': RATING_ORDER,
        },
    )
    add_total_labels_h(fig5, rating_sorted, 'PerformanceRating', 'annual_pct')
    fig5.update_layout(showlegend=True, legend=dict(orientation='h', y=-0.15),
                       xaxis=dict(title='Annualized %', range=[0, rating_sorted['annual_pct'].max() * 1.25]))
    st.plotly_chart(fig5, use_container_width=True)
    st.caption(
        "Employees without a performance rating are excluded. "
        "Unrated employees are disproportionately short-tenure staff who left before their first "
        "annual review — their attrition signal is captured in the tenure band chart, not here."
    )
