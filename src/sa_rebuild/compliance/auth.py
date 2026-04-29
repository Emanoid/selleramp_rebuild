"""Firebase Authentication via the REST Identity Toolkit API (email + password)."""
from __future__ import annotations

import os

import requests
import streamlit as st


_SIGN_IN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={key}"
)


def sign_in(email: str, password: str) -> dict:
    """
    Sign in with email + password using the Firebase Auth REST API.

    Returns a dict with keys: email, uid, id_token, refresh_token.
    Raises ValueError on bad credentials, RuntimeError on config/network issues.
    """
    api_key = os.getenv("FIREBASE_WEB_API_KEY")
    if not api_key:
        api_key = st.secrets["FIREBASE_WEB_API_KEY"]
        if not api_key:
            raise RuntimeError(
                "FIREBASE_WEB_API_KEY not set. See compliance_tool_plan.md → Step 6."
            )

    try:
        resp = requests.post(
            _SIGN_IN_URL.format(key=api_key),
            json={"email": email, "password": password, "returnSecureToken": True},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Network error during sign-in: {exc}") from exc

    if resp.status_code == 400:
        error = resp.json().get("error", {}).get("message", "INVALID_CREDENTIALS")
        if "EMAIL_NOT_FOUND" in error or "INVALID_PASSWORD" in error or "INVALID_LOGIN_CREDENTIALS" in error:
            raise ValueError("Email or password is incorrect.")
        raise ValueError(f"Sign-in failed: {error}")

    resp.raise_for_status()
    data = resp.json()
    return {
        "email": data["email"],
        "uid": data["localId"],
        "id_token": data["idToken"],
        "refresh_token": data["refreshToken"],
    }
