import sqlite3
from pathlib import Path
import pandas as pd

DB_PATH = Path(__file__).parent / 'workforce.db'

# ── Simiant brand palette ─────────────────────────────────────────────────────

# Attrition split
VOL_COLOR    = '#E07A5F'   # Muted Coral  — voluntary exits
INVOL_COLOR  = '#F2CC8F'   # Pale Sand    — involuntary exits
LAYOFF_COLOR = '#C9503A'   # Dark Coral   — layoffs
RIF_COLOR    = '#C9503A'   # Dark Coral   — RIF event markers

# General-purpose singles
PRIMARY    = '#3A7CA5'   # Open Water   — headcount lines, single-series charts
PRIMARY_DK = '#2C5F7A'   # Pacific Slate
SAGE       = '#81B29A'   # Sage         — manager %, secondary metrics, Exec dept

# Heatmap diverging scales
# Low  = coral (bad/low), Mid = sand, High = sage (good/high)
SIMIANT_DIVERGING   = [[0.0, '#E07A5F'], [0.5, '#F2CC8F'], [1.0, '#81B29A']]
# Reversed: Low = sage (good/low attrition), High = coral (bad/high attrition)
SIMIANT_DIVERGING_R = [[0.0, '#81B29A'], [0.5, '#F2CC8F'], [1.0, '#E07A5F']]

# Performance rating colors — coral (low) → sand → sage → blue (high)
RATING_COLORS = {
    'Below Expectations':     '#C9503A',
    'Inconsistent Performer': '#E07A5F',
    'Meets Expectations':     '#F2CC8F',
    'High Performer':         '#81B29A',
    'Exceeds Expectations':   '#3A7CA5',
}

# Gender colors
GENDER_COLORS = {
    'Female':       '#E07A5F',
    'Male':         '#3A7CA5',
    'Non-binary':   '#81B29A',
    'Not Declared': '#4A7D96',
}

# Sankey / band type colors
BAND_IC_COLOR  = '#3A7CA5'   # IC bands
BAND_MGR_COLOR = '#2C5F7A'   # Manager bands
BAND_VP_COLOR  = '#81B29A'   # VP

# Department colors — Alt 2 (CFO lens): Revenue / R&D / SG&A / Exec
DEPT_COLORS = {
    # Revenue / GTM
    'Sales':             '#C9503A',
    'Marketing':         '#E07A5F',
    'Customer Success':  '#EC9B80',
    # R&D / Technical
    'Engineering':       '#28607F',
    'Product':           '#3A7CA5',
    'Data Analytics':    '#5A9DC0',
    # SG&A
    'Finance':           '#1E4560',
    'HR':                '#2C5F7A',
    'Legal':             '#3D7590',
    'Operations':        '#4A7D96',
    # Executive
    'Exec':              '#81B29A',
}

RATING_ORDER = [
    'Below Expectations',
    'Inconsistent Performer',
    'Meets Expectations',
    'High Performer',
    'Exceeds Expectations',
]

TENURE_ORDER = ['< 6 mo', '6–18 mo', '1.5–3 yr', '3–5 yr', '5–8 yr', '8+ yr']


def run_query(sql: str) -> pd.DataFrame:
    """Execute a SQL query against workforce.db and return a DataFrame."""
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(sql, conn)


def get_rif_dates() -> list:
    """Return a list of datetime objects for weeks where a RIF event fired.
    Identified as weeks with >50 Layoff terminations in snapshots."""
    df = run_query("""
        SELECT SnapDate, COUNT(*) as layoffs
        FROM snapshots
        WHERE ResignationType = 'Layoff'
        GROUP BY SnapDate
        HAVING COUNT(*) > 50
        ORDER BY SnapDate
    """)
    df['SnapDate'] = pd.to_datetime(df['SnapDate'])
    return df['SnapDate'].tolist()
