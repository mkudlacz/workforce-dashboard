import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from db import run_query, DEPT_COLORS, BAND_IC_COLOR, BAND_MGR_COLOR, BAND_VP_COLOR, PRIMARY
from filters import render_sidebar_filter

st.title("Promotions & Cross-Department Moves")

start_date, end_date = render_sidebar_filter()

BAND_ORDER = ['IC1', 'IC2', 'IC3', 'M1', 'M2', 'M3', 'VP']


@st.cache_data
def load_promotion_data(start_date: str, end_date: str):
    """Detect promotions via JobBand changes and cross-dept moves via Department changes."""

    raw = run_query(f"""
        WITH lagged AS (
            SELECT
                EmployeeID,
                SnapDate,
                Department,
                JobBand,
                Role,
                IsManager,
                OrgLayer,
                TenureYears,
                LAG(JobBand)    OVER (PARTITION BY EmployeeID ORDER BY SnapDate) AS prev_band,
                LAG(Department) OVER (PARTITION BY EmployeeID ORDER BY SnapDate) AS prev_dept,
                LAG(IsManager)  OVER (PARTITION BY EmployeeID ORDER BY SnapDate) AS prev_is_mgr,
                LAG(OrgLayer)   OVER (PARTITION BY EmployeeID ORDER BY SnapDate) AS prev_layer
            FROM snapshots
            WHERE Status = 'Active'
              AND SnapDate BETWEEN '{start_date}' AND '{end_date}'
        )
        SELECT *
        FROM lagged
        WHERE prev_band IS NOT NULL
          AND (JobBand != prev_band OR Department != prev_dept)
    """)

    if raw.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    raw['SnapDate'] = pd.to_datetime(raw['SnapDate'])

    # ── Promotions: band moved UP in the order ──────────────────
    def band_idx(b):
        return BAND_ORDER.index(b) if b in BAND_ORDER else -1

    promos = raw[raw['JobBand'] != raw['prev_band']].copy()
    promos['new_idx']  = promos['JobBand'].apply(band_idx)
    promos['prev_idx'] = promos['prev_band'].apply(band_idx)
    promos = promos[promos['new_idx'] > promos['prev_idx']].copy()

    # IC→Manager crossing
    promos['ic_to_mgr'] = (
        promos['prev_band'].str.startswith('IC') & promos['JobBand'].str.startswith('M')
    )

    # Serial promotions
    promos = promos.sort_values(['EmployeeID', 'SnapDate'])
    promos['promo_num'] = promos.groupby('EmployeeID').cumcount() + 1

    # ── Cross-department moves ──────────────────────────────────
    moves = raw[
        (raw['Department'] != raw['prev_dept'])
        & (raw['prev_dept'].notna())
    ].copy()

    return raw, promos, moves, pd.DataFrame()


raw, promos, moves, _ = load_promotion_data(start_date, end_date)

st.markdown(f"Showing activity between **{start_date}** and **{end_date}**.")

# ═══════════════════════════════════════════════════════════════
# PROMOTIONS
# ═══════════════════════════════════════════════════════════════
st.header("Promotions")
st.caption("A promotion is a job band increase (e.g. IC2 → IC3, IC3 → M1). "
           "Layer-only changes (reorgs, backfills) are excluded.")

if promos.empty:
    st.info("No promotions detected in the selected date range.")
else:
    # ── Metrics ────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Promotion Events", f"{len(promos):,}")
    c2.metric("Employees Promoted", f"{promos['EmployeeID'].nunique():,}")
    c3.metric("IC → Manager Conversions", f"{promos['ic_to_mgr'].sum():,}")
    median_tenure = promos['TenureYears'].median()
    c4.metric("Median Tenure at Promotion", f"{median_tenure:.1f} yrs")

    st.divider()

    # ── Sankey: old band → new band ────────────────────────────
    st.subheader("Promotion Flow (Band → Band)")

    sankey_df = (
        promos.groupby(['prev_band', 'JobBand'], as_index=False)
        .agg(employees=('EmployeeID', 'nunique'), events=('EmployeeID', 'count'))
        .sort_values(['prev_band', 'JobBand'])
    )

    src_bands = sorted(sankey_df['prev_band'].unique(), key=lambda b: BAND_ORDER.index(b))
    tgt_bands = sorted(sankey_df['JobBand'].unique(),   key=lambda b: BAND_ORDER.index(b))

    node_labels = [f"From {b}" for b in src_bands] + [f"To {b}" for b in tgt_bands]
    src_idx = {b: i for i, b in enumerate(src_bands)}
    tgt_idx = {b: i + len(src_bands) for i, b in enumerate(tgt_bands)}

    # Color nodes by band type
    node_colors = []
    for b in src_bands + tgt_bands:
        real_band = b.replace('From ', '').replace('To ', '') if ' ' in b else b
        if real_band.startswith('IC'):
            node_colors.append(BAND_IC_COLOR)
        elif real_band.startswith('M'):
            node_colors.append(BAND_MGR_COLOR)
        else:
            node_colors.append(BAND_VP_COLOR)

    fig_sankey = go.Figure(data=[go.Sankey(
        arrangement="snap",
        node=dict(
            pad=20, thickness=20,
            line=dict(color="gray", width=0.5),
            label=node_labels,
            color=node_colors,
        ),
        link=dict(
            source=sankey_df['prev_band'].map(src_idx).tolist(),
            target=sankey_df['JobBand'].map(tgt_idx).tolist(),
            value=sankey_df['employees'].tolist(),
            customdata=sankey_df[['events', 'employees']].values,
            hovertemplate=(
                "%{source.label} → %{target.label}<br>"
                "Employees: %{value}<br>"
                "Events: %{customdata[0]}<extra></extra>"
            ),
        ),
    )])
    fig_sankey.update_layout(height=450, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig_sankey, use_container_width=True)

    # ── Promotions by department ───────────────────────────────
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Promotions by Department")
        dept_promos = (
            promos.groupby('Department', as_index=False)
            .agg(promotions=('EmployeeID', 'count'), employees=('EmployeeID', 'nunique'))
            .sort_values('promotions', ascending=True)
        )
        fig_dept = px.bar(
            dept_promos, x='promotions', y='Department', orientation='h',
            color='Department', color_discrete_map=DEPT_COLORS,
            labels={'promotions': 'Promotion Events', 'Department': ''},
            hover_data=['employees'],
        )
        fig_dept.update_layout(showlegend=False)
        st.plotly_chart(fig_dept, use_container_width=True)

    with col_b:
        st.subheader("Quarterly Promotion Trend")
        promos['quarter'] = promos['SnapDate'].dt.to_period('Q').astype(str)
        quarterly = (
            promos.groupby('quarter', as_index=False)
            .agg(
                employees_promoted=('EmployeeID', 'nunique'),
                serial_promotions=('promo_num', lambda x: (x > 1).sum()),
            )
            .sort_values('quarter')
        )
        quarterly['quarter_dt'] = pd.PeriodIndex(quarterly['quarter'], freq='Q').to_timestamp()

        q_long = quarterly.melt(
            id_vars='quarter_dt',
            value_vars=['employees_promoted', 'serial_promotions'],
            var_name='metric', value_name='count',
        )
        q_long['metric'] = q_long['metric'].map({
            'employees_promoted': 'Employees Promoted',
            'serial_promotions': 'Serial Promotions',
        })

        fig_q = px.line(
            q_long, x='quarter_dt', y='count', color='metric', markers=True,
            labels={'quarter_dt': '', 'count': 'Count', 'metric': ''},
        )
        fig_q.update_layout(legend=dict(orientation='h', y=-0.2))
        st.plotly_chart(fig_q, use_container_width=True)

    # ── Promotion paths table ──────────────────────────────────
    st.subheader("Promotion Paths")
    path_table = (
        promos.groupby(['prev_band', 'JobBand'], as_index=False)
        .agg(
            employees=('EmployeeID', 'nunique'),
            events=('EmployeeID', 'count'),
            median_tenure=('TenureYears', 'median'),
            ic_to_mgr=('ic_to_mgr', 'sum'),
        )
        .sort_values(['prev_band', 'JobBand'])
    )
    path_table['median_tenure'] = path_table['median_tenure'].round(1)
    path_table['ic_to_mgr'] = path_table['ic_to_mgr'].astype(int)
    path_table = path_table.rename(columns={
        'prev_band': 'From Band', 'JobBand': 'To Band',
        'employees': 'Employees', 'events': 'Events',
        'median_tenure': 'Median Tenure (yrs)', 'ic_to_mgr': 'IC→Mgr',
    })
    st.dataframe(path_table, hide_index=True, use_container_width=True)

# ═══════════════════════════════════════════════════════════════
# CROSS-DEPARTMENT MOVES
# ═══════════════════════════════════════════════════════════════
st.divider()
st.header("Cross-Department Moves")
st.caption("Employees who changed departments between consecutive weekly snapshots.")

if moves.empty:
    st.info("No cross-department moves detected in the selected date range.")
else:
    m1, m2 = st.columns(2)
    m1.metric("Move Events", f"{len(moves):,}")
    m2.metric("Employees Moved", f"{moves['EmployeeID'].nunique():,}")

    st.divider()

    # ── Sankey: source dept → destination dept ────────────────
    st.subheader("Department Move Flow")
    top_pairs = (
        moves.groupby(['prev_dept', 'Department'], as_index=False)
        .agg(employees=('EmployeeID', 'nunique'))
        .sort_values('employees', ascending=False)
        .head(15)
    )

    src_depts = sorted(top_pairs['prev_dept'].unique())
    tgt_depts = sorted(top_pairs['Department'].unique())
    node_labels = [f"From {d}" for d in src_depts] + [f"To {d}" for d in tgt_depts]
    src_idx = {d: i for i, d in enumerate(src_depts)}
    tgt_idx = {d: i + len(src_depts) for i, d in enumerate(tgt_depts)}
    node_colors = (
        [DEPT_COLORS.get(d, '#888') for d in src_depts] +
        [DEPT_COLORS.get(d, '#888') for d in tgt_depts]
    )

    fig_moves_sankey = go.Figure(data=[go.Sankey(
        arrangement="snap",
        node=dict(
            pad=15, thickness=20,
            line=dict(color="gray", width=0.5),
            label=node_labels,
            color=node_colors,
        ),
        link=dict(
            source=top_pairs['prev_dept'].map(src_idx).tolist(),
            target=top_pairs['Department'].map(tgt_idx).tolist(),
            value=top_pairs['employees'].tolist(),
            hovertemplate="%{source.label} → %{target.label}<br>Employees: %{value}<extra></extra>",
        ),
    )])
    fig_moves_sankey.update_layout(height=500, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig_moves_sankey, use_container_width=True)
    st.caption("Top 15 source → destination pairs by unique employees moved.")

    col_c, col_d = st.columns(2)

    with col_c:
        st.subheader("Quarterly Move Trend")
        moves['quarter'] = moves['SnapDate'].dt.to_period('Q').astype(str)
        move_q = (
            moves.groupby('quarter', as_index=False)
            .agg(employees_moved=('EmployeeID', 'nunique'))
            .sort_values('quarter')
        )
        move_q['quarter_dt'] = pd.PeriodIndex(move_q['quarter'], freq='Q').to_timestamp()
        fig_mq = px.line(
            move_q, x='quarter_dt', y='employees_moved', markers=True,
            labels={'quarter_dt': '', 'employees_moved': 'Employees Moved'},
            color_discrete_sequence=[PRIMARY],
        )
        st.plotly_chart(fig_mq, use_container_width=True)

    with col_d:
        st.subheader("Net Flow by Department")
        st.caption("Positive = net receiver of talent. Negative = net exporter.")
        outflow = moves.groupby('prev_dept', as_index=False).agg(out=('EmployeeID', 'nunique'))
        inflow  = moves.groupby('Department', as_index=False).agg(into=('EmployeeID', 'nunique'))
        net = (
            outflow.rename(columns={'prev_dept': 'Department'})
            .merge(inflow, on='Department', how='outer')
            .fillna(0)
        )
        net['net'] = (net['into'] - net['out']).astype(int)
        net = net.sort_values('net')
        fig_net = px.bar(
            net, x='net', y='Department', orientation='h',
            color='Department', color_discrete_map=DEPT_COLORS,
            labels={'net': 'Net Employees (In − Out)', 'Department': ''},
        )
        fig_net.update_layout(showlegend=False)
        st.plotly_chart(fig_net, use_container_width=True)
