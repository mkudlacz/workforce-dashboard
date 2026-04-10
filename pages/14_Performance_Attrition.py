import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from db import run_query, RATING_ORDER, VOL_COLOR, INVOL_COLOR
from filters import render_sidebar_filter

st.title("Performance & Attrition")

start_date, end_date = render_sidebar_filter()

st.markdown(
    "Performance and attrition have a counterintuitive relationship — and the data makes it "
    "visible. Across the performance spectrum, two patterns run in opposite directions. "
    "Involuntary attrition decreases as performance increases: employees rated Below "
    "Expectations are involuntarily exited at roughly 3x the rate of Exceeds Expectations "
    "employees. Voluntary attrition runs the other direction: top performers leave by choice "
    "at 32% above the average rate. The employees most likely to be managed out and the "
    "employees most likely to walk out are entirely different populations — and they require "
    "entirely different responses."
)


@st.cache_data
def load_rating_attrition(start_date: str, end_date: str) -> pd.DataFrame:
    df = run_query(f"""
        SELECT e.LatestRating AS rating,
               SUM(CASE WHEN s.Status='Terminated' AND s.ResignationType='Voluntary'
                        THEN 1 ELSE 0 END) AS vol_exits,
               SUM(CASE WHEN s.Status='Terminated' AND s.ResignationType='Involuntary'
                        THEN 1 ELSE 0 END) AS invol_exits,
               SUM(CASE WHEN s.Status='Active' THEN 1 ELSE 0 END) AS active_weeks
        FROM employees e
        JOIN snapshots s ON e.EmployeeID = s.EmployeeID
        WHERE e.LatestRating IS NOT NULL
          AND s.SnapDate BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY e.LatestRating
    """)
    df['vol_rate']   = (df['vol_exits']   / df['active_weeks'] * 52 * 100).round(2)
    df['invol_rate'] = (df['invol_exits'] / df['active_weeks'] * 52 * 100).round(2)
    df['rating'] = pd.Categorical(df['rating'], categories=RATING_ORDER, ordered=True)
    return df.sort_values('rating')


df = load_rating_attrition(start_date, end_date)


# ── Chart ─────────────────────────────────────────────────────────────────────
st.subheader("Annualized Attrition Rate by Performance Rating")

fig = go.Figure()

fig.add_trace(go.Bar(
    name='Voluntary',
    x=df['rating'].astype(str),
    y=df['vol_rate'],
    marker_color=VOL_COLOR,
    text=df['vol_rate'].apply(lambda v: f"{v:.1f}%"),
    textposition='outside',
    hovertemplate='%{x}<br>Voluntary: %{y:.1f}%<extra></extra>',
))

fig.add_trace(go.Bar(
    name='Involuntary',
    x=df['rating'].astype(str),
    y=df['invol_rate'],
    marker_color=INVOL_COLOR,
    text=df['invol_rate'].apply(lambda v: f"{v:.1f}%"),
    textposition='outside',
    hovertemplate='%{x}<br>Involuntary: %{y:.1f}%<extra></extra>',
))

# Divergence arrows: annotate the endpoints
max_vol   = df['vol_rate'].max()
max_invol = df['invol_rate'].max()

fig.add_annotation(
    x='Exceeds Expectations', y=df.loc[df['rating']=='Exceeds Expectations','vol_rate'].values[0],
    text='Vol peaks here', showarrow=True, arrowhead=2,
    ax=-70, ay=-40, font=dict(size=10, color=VOL_COLOR), arrowcolor=VOL_COLOR,
)
fig.add_annotation(
    x='Below Expectations', y=df.loc[df['rating']=='Below Expectations','invol_rate'].values[0],
    text='Invol peaks here', showarrow=True, arrowhead=2,
    ax=70, ay=-40, font=dict(size=10, color=INVOL_COLOR), arrowcolor=INVOL_COLOR,
)

fig.update_layout(
    barmode='group',
    height=440,
    margin=dict(t=10, b=10, l=10, r=10),
    yaxis_title='Annualized Rate (%)',
    xaxis_title='Performance Rating (low → high)',
    legend=dict(orientation='h', y=-0.15),
    yaxis=dict(range=[0, max(max_vol, max_invol) * 1.3]),
    hovermode='x unified',
)

st.plotly_chart(fig, use_container_width=True)
st.caption(
    "Annualized voluntary and involuntary attrition rates by performance rating. "
    "As performance increases left to right, the two series diverge: involuntary risk "
    "falls sharply, voluntary risk rises. The widening gap at the top reflects the "
    "external market premium that high performers carry."
)

# ── Callouts ──────────────────────────────────────────────────────────────────
st.divider()

col1, col2 = st.columns(2)

with col1:
    st.info(
        "**The involuntary gradient**\n\n"
        "The involuntary attrition gradient is steep and monotonic. Below Expectations "
        "employees are involuntarily exited at 1.46x the rate of average performers; "
        "Exceeds Expectations employees exit involuntarily at just 0.47x — less than half "
        "the average rate. The organization is effectively 3x more likely to exit its "
        "lowest performers than its highest. The gradient is doing what it should — but "
        "it raises a harder question: are performance ratings reliably capturing performance, "
        "or are they capturing visibility, tenure, and proximity to leadership?"
    )

with col2:
    st.info(
        "**The voluntary premium for top performers**\n\n"
        "The voluntary gradient runs the other way, and the mechanism is well-established. "
        "High performers carry strong external market value, high sensitivity to internal "
        "inequity, and lower tolerance for stagnation. Trevor, Gerhart & Boudreau (1997) "
        "documented this relationship empirically: voluntary attrition among top performers "
        "is highest when pay-for-performance differentiation is weak. The 32% voluntary "
        "premium for Exceeds Expectations is not a sign of organizational failure — it is a "
        "signal about market demand. The question it raises: are internal opportunity and "
        "recognition keeping pace with what the market is offering these employees?"
    )
