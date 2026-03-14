import sqlite3
from pathlib import Path
import pandas as pd

DB_PATH = Path(__file__).parent / 'workforce.db'

# Consistent department color map used across all pages
DEPT_COLORS = {
    'Engineering':      '#636EFA',
    'Sales':            '#EF553B',
    'Marketing':        '#00CC96',
    'HR':               '#AB63FA',
    'Finance':          '#FFA15A',
    'Operations':       '#19D3F3',
    'Product':          '#FF6692',
    'Legal':            '#B6E880',
    'Exec':             '#FF97FF',
    'Customer Success': '#FECB52',
    'Data Analytics':   '#72B7B2',
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
