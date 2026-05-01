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
st.caption(f"v{__version__} — internal tools for Amazon FBA sourcing and business operations")

st.markdown(
    """
    A suite of tools built for Central Line Group.
    Select a tool from the **sidebar** or click a card below to get started.
    """
)

st.divider()

st.subheader("Available tools")

col1, col2 = st.columns(2, gap="large")

with col1:
    st.markdown("#### 🧮 Keepa Search Tool")
    st.markdown(
        "Upload a CSV of UPCs or ASINs with your wholesale cost. "
        "Get a per-row **Buy / Caution / Skip** verdict — recommended sell price, "
        "fees, ROI, monthly sales, competition analysis, and a direct storefront link. "
        "Powered by your Keepa Pro key. Picks up where it left off if interrupted."
    )
    st.page_link("pages/1_Keepa_Search_Tool.py", label="Open Keepa Search Tool →", icon="🧮")

with col2:
    st.markdown("#### 📋 LLC Compliance Tracker")
    st.markdown(
        "Live replacement for the Excel compliance tracker. "
        "Tracks all **quarterly, annual, and one-time** filing requirements "
        "for Central Line Group LLC. Mark filings done, log confirmation numbers, "
        "see what's overdue and coming up next, and review the full audit trail "
        "of every status change. "
        "Members and company info managed in-app — no spreadsheet editing needed."
    )
    st.page_link("pages/2_LLC_Compliance.py", label="Open LLC Compliance →", icon="📋")

st.divider()

col3, col4 = st.columns(2, gap="large")

with col3:
    st.markdown("#### 📊 Keepa SellerAmp Compare")
    st.markdown(
        "Match your wholesale cost list against a **Keepa Product Viewer export** — "
        "no API key needed. Get recommended sell price, ROI, profit, and full fee breakdown "
        "for every product instantly. Multiple ASINs per UPC produce separate rows, "
        "ranked by weight match. Download the full analysis as a CSV."
    )
    st.page_link("pages/3_Keepa_Compare.py", label="Open Keepa SellerAmp Compare →", icon="📊")

with col4:
    st.markdown("#### 💰 Finance Tracker")
    st.markdown(
        "Live replacement for the Excel finance tracker. "
        "Log **expenses** (static or recurring with frequency) and **Amazon income** deposits. "
        "The built-in calculators compute totals for any date range, factoring in recurring "
        "schedules. The Profit tab breaks down revenue, expenses, tax reserve, reinvestment, "
        "and member distributions. Dashboard shows a full financial summary for any period. "
        "Login required — financial data is private."
    )
    st.page_link("pages/4_Finance_Tracker.py", label="Open Finance Tracker →", icon="💰")
