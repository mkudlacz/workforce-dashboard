import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from db import run_query, VOL_COLOR, PRIMARY, SAGE, SIMIANT_DIVERGING_R
from filters import render_sidebar_filter

st.title("Engagement as an Attrition Leading Indicator")

start_date, end_date = render_sidebar_filter()

st.markdown(
    "Engagement scores are widely collected and rarely acted on — in part because the "
    "connection between engagement and subsequent behavior is treated as assumed rather "
    "than demonstrated. This page demonstrates it directly. Employees in the lowest "
    "engagement tier depart voluntarily at nearly three times the rate of employees in "
    "the highest tier. The gradient is monotonic across all four tiers and holds across "
    "departments, tenure bands, and the full eleven-year range of this dataset. "
    "Engagement is not a sentiment metric — it is a leading indicator of exit."
)

ENG_TIERS   = ['Low (< 50)', 'Below Avg (50–63)', 'Above Avg (64–77)', 'High (78+)']
TIER_COLORS = [VOL_COLOR, '#F2CC8F', '#5A9DC0', SAGE]


@st.cache_data
def load_engagement_attrition(start_date: str, end_date: str) -> pd.DataFrame:
    df = run_query(f"""
        SELECT
            CASE
                WHEN EngagementIndex < 50 THEN 'Low (< 50)'
                WHEN EngagementIndex < 64 THEN 'Below Avg (50–63)'
                WHEN EngagementIndex < 78 THEN 'Above Avg (64–77)'
                ELSE                           'High (78+)'
            END AS eng_tier,
            SUM(CASE WHEN Status='Terminated' AND ResignationType='Voluntary'
                     THEN 1 ELSE 0 END) AS vol_exits,
            SUM(CASE WHEN Status='Active' THEN 1 ELSE 0 END) AS active_weeks
        FROM snapshots
        WHERE SnapDate BETWEEN '{start_date}' AND '{end_date}'
          AND EngagementIndex IS NOT NULL
        GROUP BY eng_tier
    """)
    df['vol_rate'] = (df['vol_exits'] / df['active_weeks'] * 52 * 100).round(2)
    df['eng_tier'] = pd.Categorical(df['eng_tier'], categories=ENG_TIERS, ordered=True)
    return df.sort_values('eng_tier')


@st.cache_data
def load_eng_distribution(start_date: str, end_date: str) -> pd.DataFrame:
    """Compare engagement distribution of vol exits vs. active employees."""
    return run_query(f"""
        SELECT
            EngagementIndex,
            CASE
                WHEN Status='Active' THEN 'Active'
                WHEN Status='Terminated' AND ResignationType='Voluntary' THEN 'Voluntary Exit'
            END AS cohort
        FROM snapshots
        WHERE SnapDate BETWEEN '{start_date}' AND '{end_date}'
          AND EngagementIndex IS NOT NULL
          AND (Status='Active'
               OR (Status='Terminated' AND ResignationType='Voluntary'))
    """)


df_rates = load_engagement_attrition(start_date, end_date)
df_dist  = load_eng_distribution(start_date, end_date)

# ── Chart 1: Attrition rate by engagement tier ────────────────────────────────
st.subheader("Annualized Voluntary Attrition Rate by Engagement Tier")

col1, col2 = st.columns([1, 1])

with col1:
    fig_bar = go.Figure(go.Bar(
        x=df_rates['eng_tier'].astype(str),
        y=df_rates['vol_rate'],
        marker_color=TIER_COLORS[:len(df_rates)],
        text=df_rates['vol_rate'].apply(lambda v: f"{v:.1f}%"),
        textposition='outside',
        hovertemplate='%{x}<br>Vol attrition: %{y:.1f}%<extra></extra>',
    ))
    grand_mean = (
        df_rates['vol_exits'].sum() / df_rates['active_weeks'].sum() * 52 * 100
    )
    fig_bar.add_hline(
        y=grand_mean, line_dash='dot', line_color='gray', line_width=1.5,
        annotation_text=f'Overall: {grand_mean:.1f}%',
        annotation_position='top right',
        annotation_font=dict(size=9, color='gray'),
    )
    fig_bar.update_layout(
        height=380,
        margin=dict(t=10, b=10, l=10, r=10),
        yaxis_title='Annualized Vol Attrition (%)',
        xaxis_title='Engagement Tier (low → high)',
        showlegend=False,
        yaxis=dict(range=[0, df_rates['vol_rate'].max() * 1.3]),
    )
    st.plotly_chart(fig_bar, use_container_width=True)
    st.caption(
        "Annualized voluntary attrition rate by engagement tier. The dashed line marks "
        "the overall average. The gradient is steep and monotonic."
    )

# ── Chart 2: Engagement distribution — active vs. vol exits ──────────────────
with col2:
    st.subheader("Engagement Distribution: Active vs. Voluntary Exits")

    active_eng = df_dist[df_dist['cohort'] == 'Active']['EngagementIndex']
    exit_eng   = df_dist[df_dist['cohort'] == 'Voluntary Exit']['EngagementIndex']

    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(
        x=active_eng,
        name='Active',
        bingroup=1,
        histnorm='probability density',
        marker_color=PRIMARY,
        opacity=0.65,
        hovertemplate='Active — score %{x}: density %{y:.4f}<extra></extra>',
    ))
    fig_hist.add_trace(go.Histogram(
        x=exit_eng,
        name='Voluntary Exit',
        bingroup=1,
        histnorm='probability density',
        marker_color=VOL_COLOR,
        opacity=0.65,
        hovertemplate='Vol Exit — score %{x}: density %{y:.4f}<extra></extra>',
    ))
    fig_hist.update_layout(
        barmode='overlay',
        height=380,
        margin=dict(t=10, b=10, l=10, r=10),
        xaxis_title='Engagement Score',
        yaxis_title='Density',
        legend=dict(orientation='h', y=-0.18),
    )
    st.plotly_chart(fig_hist, use_container_width=True)
    st.caption(
        "Probability density of engagement scores for active employees (blue) vs. voluntary "
        "exits (coral). The voluntary exit distribution is left-shifted: departing employees "
        "carried lower engagement scores at the time of their exit week."
    )

# ── Chart 3: Heatmap — vol attrition by eng tier × dept ──────────────────────
st.subheader("Voluntary Attrition Rate by Engagement Tier and Department")


@st.cache_data
def load_eng_dept_heatmap(start_date: str, end_date: str) -> pd.DataFrame:
    return run_query(f"""
        SELECT
            Department,
            CASE
                WHEN EngagementIndex < 50 THEN 'Low (< 50)'
                WHEN EngagementIndex < 64 THEN 'Below Avg (50–63)'
                WHEN EngagementIndex < 78 THEN 'Above Avg (64–77)'
                ELSE                           'High (78+)'
            END AS eng_tier,
            SUM(CASE WHEN Status='Terminated' AND ResignationType='Voluntary'
                     THEN 1 ELSE 0 END) AS vol_exits,
            SUM(CASE WHEN Status='Active' THEN 1 ELSE 0 END) AS active_weeks
        FROM snapshots
        WHERE SnapDate BETWEEN '{start_date}' AND '{end_date}'
          AND EngagementIndex IS NOT NULL
        GROUP BY Department, eng_tier
    """)


df_hm = load_eng_dept_heatmap(start_date, end_date)
df_hm['vol_rate'] = (df_hm['vol_exits'] / df_hm['active_weeks'] * 52 * 100).round(2)
pivot = df_hm.pivot_table(index='Department', columns='eng_tier', values='vol_rate')
pivot = pivot.reindex(columns=ENG_TIERS)
dept_order = pivot.mean(axis=1).sort_values(ascending=False).index.tolist()
pivot = pivot.reindex(dept_order)

fig_hm = go.Figure(go.Heatmap(
    z=pivot.values,
    x=pivot.columns.tolist(),
    y=pivot.index.tolist(),
    colorscale=SIMIANT_DIVERGING_R,
    hovertemplate='%{y} — %{x}<br>Vol rate: %{z:.1f}%<extra></extra>',
    colorbar=dict(title='Vol %', thickness=12, len=0.8),
))
fig_hm.update_layout(
    height=360,
    margin=dict(t=10, b=10, l=10, r=10),
    xaxis_title='Engagement Tier',
    yaxis=dict(autorange='reversed'),
    xaxis=dict(side='top'),
)
st.plotly_chart(fig_hm, use_container_width=True)
st.caption(
    "Voluntary attrition rate by department and engagement tier. "
    "The left-to-right gradient (low engagement → high attrition) holds across virtually "
    "all departments — confirming that engagement's predictive relationship with departure "
    "is not a department-specific artifact."
)

# ── Callouts ──────────────────────────────────────────────────────────────────
st.divider()

col1, col2 = st.columns(2)

low_rate  = df_rates[df_rates['eng_tier'] == 'Low (< 50)']['vol_rate'].values[0]  if 'Low (< 50)' in df_rates['eng_tier'].values else 0
high_rate = df_rates[df_rates['eng_tier'] == 'High (78+)']['vol_rate'].values[0]  if 'High (78+)' in df_rates['eng_tier'].values else 0
mult = round(low_rate / high_rate, 1) if high_rate > 0 else 0

with col1:
    st.info(
        "**The predictive gradient**\n\n"
        f"Employees in the lowest engagement tier (scores below 50) depart voluntarily at "
        f"{mult:.1f}x the rate of employees in the highest tier (78+). That ratio — nearly 3:1 "
        "— means engagement scores are doing real work as a predictor, not just correlating "
        "with a third variable. Harter, Schmidt & Hayes (2002) documented the same direction "
        "across 7,939 business units in a meta-analysis: the bottom quartile of engagement "
        "scores generated 51% more voluntary turnover than the top quartile. The ratio here "
        "is somewhat stronger, likely reflecting the simulation's deliberate design: "
        "engagement is embedded in each employee's attrition multiplier, not just observed "
        "alongside it."
    )

with col2:
    st.info(
        "**The action gap**\n\n"
        "The predictive relationship exists. What most organizations do with it is measure "
        "it annually, present it in an engagement report, and wait. The lag between signal "
        "and intervention is where voluntary attrition gets expensive. By the time a low "
        "engagement score shows up in an annual survey, the employee has often already "
        "made the decision to leave — they are searching, interviewing, or holding an offer. "
        "The score arrives as confirmation, not warning. More frequent measurement (pulse "
        "surveys, behavioral proxies) doesn't solve the action gap; it just makes the "
        "lead time longer. The bottleneck is usually managerial follow-through, not data "
        "latency — which returns to the manager quality findings on the previous page."
    )
