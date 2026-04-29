"""Cached Firestore client — works with a local JSON file or Streamlit Cloud Secrets."""
from __future__ import annotations

import json
import os
from pathlib import Path
import base64


from dotenv import load_dotenv
import streamlit as st

# Load .env on import so env vars are available regardless of entry point
load_dotenv()


@st.cache_resource(show_spinner=False)
def get_db():
    """Return a Firestore client, initialising Firebase Admin SDK once per process."""
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError as e:
        raise RuntimeError("firebase-admin not installed. Run: pip install firebase-admin") from e

    if firebase_admin._apps:
        return firestore.client()

    # Option A: JSON content stored in Streamlit Cloud Secrets
    sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    b64 = os.getenv("FIREBASE_SERVICE_ACCOUNT_B64")
    if b64:
        sa_json = base64.b64decode(b64).decode("utf-8")
        sa_dict = json.loads(sa_json)
        cred = credentials.Certificate(sa_dict)
    elif sa_json:
        sa_dict = json.loads(sa_json)
        cred = credentials.Certificate(sa_dict)
    else:
        # Option B: path to a local JSON file
        sa_path = Path(os.getenv("FIREBASE_SERVICE_ACCOUNT", "service_account.json"))
        if not sa_path.exists():
            raise FileNotFoundError(
                f"Service account not found at '{sa_path}'.\n"
                "Set FIREBASE_SERVICE_ACCOUNT env var or paste JSON into "
                "FIREBASE_SERVICE_ACCOUNT_JSON. See compliance_tool_plan.md."
            )
        cred = credentials.Certificate(str(sa_path))

    firebase_admin.initialize_app(cred)
    return firestore.client()


def firebase_configured() -> bool:
    """Return True if enough env vars are present to attempt a connection."""
    has_sa = bool(
        os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        or Path(os.getenv("FIREBASE_SERVICE_ACCOUNT", "service_account.json")).exists()
    )
    has_api_key = bool(os.getenv("FIREBASE_WEB_API_KEY"))
    return has_sa and has_api_key
