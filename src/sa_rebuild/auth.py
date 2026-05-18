"""Shared Firebase authentication used by all apps."""
from __future__ import annotations

import os
from typing import Optional

import requests
import streamlit as st

_SIGN_IN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={key}"
)

_VALID_ROLES = ("admin", "editor")


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


def _resolve_role(id_token: str) -> str:
    """Verify the Firebase ID token and return its 'role' custom claim.

    The role lives in a custom claim baked into a Google-signed JWT and is
    settable only via the Admin SDK (`scripts/grant_role.py`) — a user cannot
    read, forge, or change their own. Verification (signature + expiry) happens
    here, server-side. Any failure falls back to 'editor' (least privilege).
    """
    try:
        # Force Admin SDK initialisation before verifying the token.
        from sa_rebuild.compliance.firebase_client import get_db
        get_db()
        from firebase_admin import auth as admin_auth
        decoded = admin_auth.verify_id_token(id_token)
    except Exception:
        return "editor"
    role = decoded.get("role")
    return role if role in _VALID_ROLES else "editor"


def login_wall(
    session_key: str, app_name: str, required_role: Optional[str] = None
) -> Optional[dict]:
    """Render a login form and gate the page.

    Blocks rendering via st.stop() until the visitor is authenticated. The
    returned dict carries a verified `role` ('admin' | 'editor'). If
    `required_role` is set, an authenticated user lacking that role is also
    blocked — authentication alone is never sufficient.
    """
    ss = st.session_state
    user = ss.get(session_key)

    if not user:
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
                    account = sign_in(email.strip(), password)
                    account["role"] = _resolve_role(account["id_token"])
                    ss[session_key] = account
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
                except RuntimeError:
                    st.error(
                        "Sign-in is temporarily unavailable. "
                        "Please contact the administrator."
                    )
        st.stop()
        return None

    if required_role == "admin" and user.get("role") != "admin":
        st.error(
            f"🔒 **{app_name}** is restricted to admin accounts. "
            f"You are signed in as {user.get('email', '')} "
            f"(role: {user.get('role', 'editor')})."
        )
        if st.button("Sign out", key=f"{session_key}_role_signout"):
            del ss[session_key]
            st.rerun()
        st.stop()
        return None

    return user


def list_users_with_roles() -> list:
    """List every Firebase Auth account with its assigned role.

    Role comes from the custom claim; an account with no valid claim is
    reported as 'editor' (the app's least-privilege default) and flagged
    `assigned=False`. Requires the Admin SDK.
    """
    from sa_rebuild.compliance.firebase_client import get_db
    get_db()  # ensure the Admin SDK app is initialised
    from firebase_admin import auth as admin_auth

    rows = []
    for record in admin_auth.list_users().iterate_all():
        role = (record.custom_claims or {}).get("role")
        rows.append({
            "email": record.email or "(no email)",
            "role": role if role in _VALID_ROLES else "editor",
            "assigned": role in _VALID_ROLES,
            "uid": record.uid,
        })
    # admins first, then alphabetical by email
    rows.sort(key=lambda r: (r["role"] != "admin", r["email"].lower()))
    return rows


def render_user_roles() -> None:
    """Render a read-only table of every account and its role.

    Roles are managed only via `scripts/grant_role.py` — this panel is purely
    informational.
    """
    import pandas as pd

    try:
        rows = list_users_with_roles()
    except Exception as exc:  # network / permissions / SDK issues
        st.warning(f"Could not load user accounts: {exc}")
        return

    df = pd.DataFrame([
        {
            "Email": r["email"],
            "Role": r["role"] if r["assigned"] else f"{r['role']} (default)",
            "UID": r["uid"],
        }
        for r in rows
    ])
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.caption(f"{len(rows)} account(s) · read-only.")
