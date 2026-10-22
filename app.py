"""Streamlit app for scoring recorded chess classes.

Run with:  streamlit run app.py
"""

from pathlib import Path

import streamlit as st

VIEWS = Path(__file__).resolve().parent / "views"

st.set_page_config(page_title="Class Scorer", page_icon="♟️", layout="wide")
st.navigation([
    st.Page(VIEWS / "score.py", title="Score a class", icon="♟️", default=True),
    st.Page(VIEWS / "settings.py", title="Rubric weights", icon="⚙️"),
]).run()
