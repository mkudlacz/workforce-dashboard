import streamlit as st
import calendar
from datetime import date


def _generate_quarters() -> list[str]:
    """All quarters from 2015-Q1 through the current quarter."""
    today = date.today()
    current_q = (today.month - 1) // 3 + 1
    quarters = []
    year, q = 2015, 1
    while (year, q) <= (today.year, current_q):
        quarters.append(f"{year}-Q{q}")
        q += 1
        if q > 4:
            q, year = 1, year + 1
    return quarters


def quarter_to_dates(q_str: str) -> tuple[str, str]:
    """'2020-Q3'  →  ('2020-07-01', '2020-09-30')"""
    year_s, q_s   = q_str.split('-Q')
    year, q       = int(year_s), int(q_s)
    start_month   = (q - 1) * 3 + 1
    end_month     = q * 3
    last_day      = calendar.monthrange(year, end_month)[1]
    return (
        f"{year}-{start_month:02d}-01",
        f"{year}-{end_month:02d}-{last_day:02d}",
    )


def render_sidebar_filter() -> tuple[str, str]:
    """
    Render a quarterly range slider in the sidebar.
    Persists selection in session_state so the chosen range survives
    page navigation.
    Returns (start_date, end_date) as 'YYYY-MM-DD' strings ready for SQL.
    """
    quarters = _generate_quarters()
    default  = (quarters[-20], quarters[-1])

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📅 Date Range")

    selected = st.sidebar.select_slider(
        "Quarter range",
        options=quarters,
        value=st.session_state.get('quarter_range', default),
        key='quarter_range',
    )

    start_date, _ = quarter_to_dates(selected[0])
    _, end_date   = quarter_to_dates(selected[1])
    st.sidebar.caption(f"{start_date}  →  {end_date}")

    return start_date, end_date
