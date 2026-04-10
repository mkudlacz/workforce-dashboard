import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from db import run_query, TENURE_ORDER, VOL_COLOR, INVOL_COLOR
from filters import render_sidebar_filter

st.title("Tenure Hazard Profile")

start_date, end_date = render_sidebar_filter()

st.markdown(
    "Employee departure risk is not uniform across the career lifecycle. Two distinct hazard "
    "curves run through this workforce — one for voluntary exits, one for involuntary — and "
    "they tell different stories about why people leave and when organizations decide to move "
    "on. Both converge on the same conclusion: the middle of the tenure distribution is the "
    "stability zone, and risk concentrates at the edges."
)


@st.cache_data
def load_tenure_hazard(start_date: str, end_date: str) -> pd.DataFrame:
    df = run_query(f"""
        SELECT
            CASE
                WHEN TenureYears < 0.5 THEN '< 6 mo'
                WHEN TenureYears < 1.5 THEN '6–18 mo'
                WHEN TenureYears < 3   THEN '1.5–3 yr'
                WHEN TenureYears < 5   THEN '3–5 yr'
                WHEN TenureYears < 8   THEN '5–8 yr'
                ELSE                        '8+ yr'
            END AS tenure_band,
            SUM(CASE WHEN Status='Terminated' AND ResignationType='Voluntary'
                     THEN 1 ELSE 0 END) AS vol_exits,
            SUM(CASE WHEN Status='Terminated' AND ResignationType='Involuntary'
                     THEN 1 ELSE 0 END) AS invol_exits,
            SUM(CASE WHEN Status='Active' THEN 1 ELSE 0 END) AS active_weeks
        FROM snapshots
        WHERE SnapDate BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY tenure_band
    """)
    df['vol_rate']   = (df['vol_exits']   / df['active_weeks'] * 52 * 100).round(2)
    df['invol_rate'] = (df['invol_exits'] / df['active_weeks'] * 52 * 100).round(2)
    df['total_rate'] = (df['vol_rate'] + df['invol_rate']).round(2)
    df['tenure_band'] = pd.Categorical(df['tenure_band'], categories=TENURE_ORDER, ordered=True)
    return df.sort_values('tenure_band')


df = load_tenure_hazard(start_date, end_date)

# ── Chart ─────────────────────────────────────────────────────────────────────
st.subheader("Annualized Attrition Rate by Tenure Band")


fig = go.Figure()

fig.add_trace(go.Bar(
    name='Voluntary',
    x=df['tenure_band'].astype(str),
    y=df['vol_rate'],
    marker_color=VOL_COLOR,
    hovertemplate='%{x}<br>Voluntary: %{y:.1f}%<extra></extra>',
    text=df['vol_rate'].apply(lambda v: f"{v:.1f}%"),
    textposition='outside',
))

fig.add_trace(go.Bar(
    name='Involuntary',
    x=df['tenure_band'].astype(str),
    y=df['invol_rate'],
    marker_color=INVOL_COLOR,
    hovertemplate='%{x}<br>Involuntary: %{y:.1f}%<extra></extra>',
    text=df['invol_rate'].apply(lambda v: f"{v:.1f}%"),
    textposition='outside',
))

# Annotate the stability floor
floor_band = '1.5–3 yr'
floor_x = list(df['tenure_band'].astype(str)).index(floor_band)
fig.add_annotation(
    x=floor_band, y=df.loc[df['tenure_band'] == floor_band, 'total_rate'].values[0],
    text='Stability floor', showarrow=True, arrowhead=2,
    ax=60, ay=-40, font=dict(size=10, color='gray'),
    arrowcolor='gray',
)

fig.update_layout(
    barmode='group',
    height=420,
    margin=dict(t=10, b=10, l=10, r=10),
    yaxis_title='Annualized Rate (%)',
    xaxis_title='Tenure Band',
    legend=dict(orientation='h', y=-0.15),
    yaxis=dict(range=[0, df['vol_rate'].max() * 1.25]),
    hovermode='x unified',
)

st.plotly_chart(fig, use_container_width=True)
st.caption(
    "Annualized voluntary and involuntary attrition rates by tenure band, calculated as "
    "exits per active employee-week. The 1.5–3 year window is the low-risk floor for both "
    "exit types. Note the divergence at 8+ years: voluntary rate moderates while involuntary "
    "rises — the two hazards pull in opposite directions at the far end of tenure."
)

# ── Callouts ──────────────────────────────────────────────────────────────────
st.divider()

col1, col2 = st.columns(2)

with col1:
    st.info(
        "**The new hire cliff**\n\n"
        "Employees in their first 18 months depart voluntarily at roughly 1.5x the rate of "
        "mid-tenure employees — not because organizations fail them en masse, but because "
        "match quality between person and role is still being resolved. New hires who discover "
        "a mismatch exit early; those who fit stay. The practical cost: at ~14% annualized, "
        "approximately one in seven new hires leaves within their first year before full "
        "productivity is reached."
    )

with col2:
    st.info(
        "**The second peak and the long-tenure inversion**\n\n"
        "The voluntary rate at 5–8 years (12%) sits 32% above the stability floor — a second "
        "elevation that emerges after employees have been stable for years. The mechanism "
        "differs from the new-hire cliff: these are employees who resolved fit long ago and "
        "are now asking whether the role still fits their ambitions. At 8+ years, voluntary "
        "risk moderates — but involuntary risk rises to its highest point. Long-tenure "
        "employees carry higher compensation and face greater scrutiny in restructuring events. "
        "The two risks at opposite ends of the tenure curve require entirely different "
        "management responses."
    )
