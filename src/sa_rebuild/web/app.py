"""Entry point — wires up navigation and sets global page config."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2]  # .../src
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

st.set_page_config(
    page_title="CentralLine Sourcing Toolbox",
    page_icon="📦",
    layout="wide",
)

pg = st.navigation([
    st.Page("home.py", title="CentralLine Tools", icon="📦", default=True),
    st.Page("pages/1_FBA_Calculator.py", title="FBA Calculator", icon="🧮"),
])
pg.run()
