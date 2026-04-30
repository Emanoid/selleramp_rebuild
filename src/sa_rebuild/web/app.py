"""Entry point — wires up navigation and sets global page config."""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="CentralLine Sourcing Toolbox",
    page_icon="📦",
    layout="wide",
)

pg = st.navigation([
    st.Page("home.py", title="CentralLine Tools", icon="📦", default=True),
    st.Page("pages/1_FBA_Calculator.py", title="FBA Calculator", icon="🧮"),
    st.Page("pages/2_LLC_Compliance.py", title="LLC Compliance", icon="📋"),
    st.Page("pages/3_Keepa_Compare.py", title="Keepa SellerAmp Compare", icon="📊"),
])
pg.run()
