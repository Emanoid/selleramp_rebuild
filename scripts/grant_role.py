#!/usr/bin/env python3
"""
Assign a role to a Firebase user for the CentralLine web apps.

Roles are stored as Firebase Auth *custom claims*. A claim is embedded in a
Google-signed ID token and is settable only with the Admin SDK — a user cannot
read, forge, or change their own role. This script is the only way to assign
roles (there is no in-app role UI, by design); run it whenever a member joins
or a role changes. It is a permanent maintenance tool, not a one-off migration.

Roles
  admin   Full access to LLC Compliance and Finance Tracker; sees all data.
  
  editor  Finance Tracker only; sees and manages only their own entries.
          (LLC Compliance is admin-only and rejects editors.)

Usage
  python scripts/grant_role.py <email> <admin|editor>
  python scripts/grant_role.py <email> admin --backfill

  --backfill  (admin only) Assign owner_uid = <this user> to every existing
              finance_expenses / finance_income document that lacks one — run
              once so pre-existing data has an owner. Idempotent: re-running
              only touches documents still missing an owner, so it never goes
              stale.

Examples
  # New bookkeeper joins — Finance Tracker only, sees just their own rows.
  python scripts/grant_role.py bookkeeper@centralline.com editor

  # Promote an existing account to full admin (LLC Compliance + all data).
  python scripts/grant_role.py partner@centralline.com admin

  # Demote an admin back to editor (re-run with the other role; the claim
  # is simply overwritten).
  python scripts/grant_role.py partner@centralline.com editor

  # First-time setup: make the founding account an admin AND claim every
  # pre-existing finance row for them so it is not orphaned. Run once.
  python scripts/grant_role.py you@centralline.com admin --backfill

The user must sign out and back in for a role change to take effect.

Prerequisites
  - The email must already exist as a Firebase account (Authentication → Users);
    this script assigns a role, it does not create accounts.
  - Firebase credentials must be reachable the same way the apps load them — a
    service_account.json in the repo root, or the FIREBASE_SERVICE_ACCOUNT* env
    vars (see sa_rebuild.compliance.firebase_client).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))


def _backfill_owner(db, uid: str) -> int:
    """Set owner_uid on finance docs that have none. Returns the count touched."""
    touched = 0
    for collection in ("finance_expenses", "finance_income"):
        for doc in db.collection(collection).stream():
            if doc.to_dict().get("owner_uid"):
                continue
            doc.reference.update({"owner_uid": uid})
            touched += 1
    return touched


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assign an admin/editor role to a Firebase user.",
    )
    parser.add_argument("email", help="Email of an existing Firebase account.")
    parser.add_argument("role", choices=("admin", "editor"))
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Assign all owner-less finance docs to this admin (admin role only).",
    )
    args = parser.parse_args()

    if args.backfill and args.role != "admin":
        sys.exit("--backfill can only be used with the 'admin' role.")

    # get_db() loads .env, initialises the Admin SDK, and returns Firestore.
    from sa_rebuild.compliance.firebase_client import get_db

    db = get_db()
    from firebase_admin import auth

    try:
        user = auth.get_user_by_email(args.email)
    except auth.UserNotFoundError:
        sys.exit(
            f"No Firebase account found for {args.email!r}. "
            "Create the account in the Firebase console first."
        )

    # Preserve any other custom claims; only (re)set 'role'.
    claims = dict(user.custom_claims or {})
    claims["role"] = args.role
    auth.set_custom_user_claims(user.uid, claims)
    print(f"OK  {args.email}  ->  role = {args.role}   (uid {user.uid})")

    if args.backfill:
        count = _backfill_owner(db, user.uid)
        print(f"OK  backfilled owner_uid on {count} finance document(s).")

    print("->  The user must sign out and back in for the change to take effect.")


if __name__ == "__main__":
    main()
