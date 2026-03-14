import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
from db import run_query, DEPT_COLORS

st.set_page_config(page_title="Employee Explorer", page_icon="🔍", layout="wide")
st.title("🔍 Employee Explorer")

st.caption(
    "Browse and filter the full employee roster. "
    "All columns reflect the employee's **final state** (current for active employees, "
    "at-termination for former employees)."
)


@st.cache_data
def load_employees():
    return run_query("""
        SELECT
            EmployeeID,
            Name,
            Department,
            Role,
            JobBand,
            OrgLayer,
            CASE WHEN IsManager = 1 THEN 'Yes' ELSE 'No' END AS Manager,
            Status,
            Gender,
            RaceEthnicity,
            Location,
            HireDate,
            TerminationDate,
            ResignationType,
            FTE,
            LatestEngagement,
            LatestRating,
            ManagerID,
            COALESCE(ManagerQuality, '—') AS ManagerQuality
        FROM employees
        ORDER BY EmployeeID
    """)


df = load_employees()

# ── Sidebar filters ──────────────────────────────────────────────────────────
st.sidebar.header("Filters")

# Status
status_opts = sorted(df['Status'].unique())
sel_status = st.sidebar.multiselect("Status", status_opts, default=status_opts)

# Department
dept_opts = sorted(df['Department'].unique())
sel_dept = st.sidebar.multiselect("Department", dept_opts, default=dept_opts)

# Job Band
band_order = ['IC1', 'IC2', 'IC3', 'M1', 'M2', 'M3', 'VP']
band_opts = [b for b in band_order if b in df['JobBand'].unique()]
sel_band = st.sidebar.multiselect("Job Band", band_opts, default=band_opts)

# Manager
sel_mgr = st.sidebar.multiselect("Manager?", ['Yes', 'No'], default=['Yes', 'No'])

# Performance Rating
rating_opts = sorted(df['LatestRating'].dropna().unique())
sel_rating = st.sidebar.multiselect("Latest Rating", rating_opts, default=rating_opts)
include_unrated = st.sidebar.checkbox("Include unrated employees", value=True)

# Gender
gender_opts = sorted(df['Gender'].unique())
sel_gender = st.sidebar.multiselect("Gender", gender_opts, default=gender_opts)

# Location
loc_opts = sorted(df['Location'].unique())
sel_loc = st.sidebar.multiselect("Location", loc_opts, default=loc_opts)

# Engagement range
eng_min = int(df['LatestEngagement'].min()) if df['LatestEngagement'].notna().any() else 32
eng_max = int(df['LatestEngagement'].max()) if df['LatestEngagement'].notna().any() else 96
sel_eng = st.sidebar.slider("Engagement Range", eng_min, eng_max, (eng_min, eng_max))

# Resignation Type (only relevant for terminated)
resign_opts = sorted(df['ResignationType'].dropna().unique())
sel_resign = st.sidebar.multiselect("Resignation Type", resign_opts, default=resign_opts)

# ── Apply filters ─────────────────────────────────────────────────────────────
filtered = df[
    (df['Status'].isin(sel_status))
    & (df['Department'].isin(sel_dept))
    & (df['JobBand'].isin(sel_band))
    & (df['Manager'].isin(sel_mgr))
    & (df['Gender'].isin(sel_gender))
    & (df['Location'].isin(sel_loc))
    & (df['LatestEngagement'].between(sel_eng[0], sel_eng[1]) | df['LatestEngagement'].isna())
]

# Rating filter
if include_unrated:
    filtered = filtered[
        (filtered['LatestRating'].isin(sel_rating)) | (filtered['LatestRating'].isna())
    ]
else:
    filtered = filtered[filtered['LatestRating'].isin(sel_rating)]

# Resignation type — only filter terminated employees; keep all active
filtered = filtered[
    (filtered['Status'] == 'Active')
    | (filtered['ResignationType'].isin(sel_resign))
]

# ── Summary metrics ──────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Showing", f"{len(filtered):,}")
c2.metric("Active", f"{(filtered['Status'] == 'Active').sum():,}")
c3.metric("Terminated", f"{(filtered['Status'] == 'Terminated').sum():,}")
avg_eng = filtered['LatestEngagement'].mean()
c4.metric("Avg Engagement", f"{avg_eng:.1f}" if pd.notna(avg_eng) else "—")

# ── Search ────────────────────────────────────────────────────────────────────
search = st.text_input("Search by name or Employee ID", "")
if search:
    mask = (
        filtered['Name'].str.contains(search, case=False, na=False)
        | filtered['EmployeeID'].str.contains(search, case=False, na=False)
    )
    filtered = filtered[mask]

# ── Display table ─────────────────────────────────────────────────────────────
st.dataframe(
    filtered,
    use_container_width=True,
    height=600,
    hide_index=True,
    column_config={
        "EmployeeID": st.column_config.TextColumn("ID", width="small"),
        "LatestEngagement": st.column_config.NumberColumn("Engagement", format="%d"),
        "FTE": st.column_config.NumberColumn("FTE", format="%.2f"),
        "OrgLayer": st.column_config.NumberColumn("Layer", format="%d"),
    },
)

st.caption(f"Showing {len(filtered):,} of {len(df):,} employees")
