"""Home / landing page — shown when no tool is selected."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve()
_SRC = _HERE.parents[2]  # .../src
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from sa_rebuild import __version__

st.title("📦 CentralLine Sourcing Toolbox")
st.caption(f"v{__version__} — internal tools for Amazon FBA product sourcing")

st.markdown(
    """
    A suite of sourcing tools built for CentralLine Group.
    Select a tool from the **sidebar** to get started.
    """
)

st.divider()

st.subheader("Available tools")

col1, col2 = st.columns(2, gap="large")

with col1:
    st.markdown("#### FBA Calculator")
    st.markdown(
        "Upload a CSV of UPCs or ASINs with your wholesale cost. "
        "Get a per-row Buy / Caution / Skip verdict — recommended sell price, "
        "fees, ROI, monthly sales, competition analysis, and a direct storefront link. "
        "Powered by your Keepa Pro key."
    )
    st.info("Select **FBA Calculator** in the sidebar to open this tool.")
