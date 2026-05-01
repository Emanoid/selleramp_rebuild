"""Shared Firebase authentication used by all apps."""
from __future__ import annotations

import os
from typing import Optional

import requests
import streamlit as st

_SIGN_IN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={key}"
)


def sign_in(email: str, password: str) -> dict:
    """Sign in via Firebase Auth REST API. Returns {email, uid, id_token, refresh_token}."""
    api_key = os.getenv("FIREBASE_WEB_API_KEY")
    if not api_key:
        try:
            api_key = st.secrets["FIREBASE_WEB_API_KEY"]
        except Exception:
            pass
    if not api_key:
        raise RuntimeError(
            "FIREBASE_WEB_API_KEY not set. See README → Environment variables."
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
        if any(k in error for k in ("EMAIL_NOT_FOUND", "INVALID_PASSWORD", "INVALID_LOGIN_CREDENTIALS")):
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


def login_wall(session_key: str, app_name: str) -> Optional[dict]:
    """Render a login form; block rendering via st.stop() if not authenticated."""
    ss = st.session_state
    if ss.get(session_key):
        return ss[session_key]

    st.markdown(
        f"<h2 style='margin-bottom:0'>🔐 {app_name} Login</h2>"
        "<p style='color:grey'>Central Line Group LLC</p>",
        unsafe_allow_html=True,
    )
    with st.form(f"{session_key}_login", clear_on_submit=False):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")

    if submitted:
        if not email or not password:
            st.error("Enter your email and password.")
        else:
            try:
                user = sign_in(email.strip(), password)
                ss[session_key] = user
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except RuntimeError as exc:
                st.error(f"Configuration error: {exc}")
    st.stop()
    return None
