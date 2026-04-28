"""Entry point — sets global page config and renders the home landing page."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2]  # .../src
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from sa_rebuild import __version__

st.set_page_config(
    page_title="FBA Toolbox",
    page_icon="📦",
    layout="wide",
)

st.title("📦 FBA Toolbox")
st.caption(f"v{__version__}")

st.markdown(
    """
    A collection of tools for Amazon FBA sourcing and analysis.
    Select a tool from the **sidebar** to get started.
    """
)

st.divider()

st.subheader("Available tools")

col1, col2 = st.columns(2, gap="large")

with col1:
    st.markdown("#### FBA Calculator")
    st.markdown(
        "Upload a CSV of UPCs/ASINs and wholesale costs. "
        "Get a per-row Buy / Caution / Skip report powered by Keepa — "
        "fees, ROI, monthly sales, competition, and a recommended sell price."
    )
    st.info("Select **FBA Calculator** in the sidebar to open this tool.")
