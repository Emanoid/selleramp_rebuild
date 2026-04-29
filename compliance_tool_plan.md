# LLC Compliance Tool — Build Plan

**Branch:** `llc_compliance_tool`
**Tool:** Second page in the CentralLine Sourcing Toolbox
**Purpose:** Replace the Excel compliance tracker with a live, multi-user web app
backed by Firebase — checkoffs, history, recurring filing management.

---

## What is being built

A Streamlit page (`pages/2_LLC_Compliance.py`) gated behind email/password login.
It mirrors the 4 tabs of the Excel workbook:

| Excel tab | Web tab | What it contains |
|---|---|---|
| Dashboard | Dashboard | Done/total metrics, overdue alerts, next-up deadlines, quick reference |
| Quarterly | Quarterly | NJ Sales Tax, Federal + NJ estimated tax — per member, pre-populated |
| Annual | Annual | Form 1065, NJ-1065, personal 1040s, NJ Annual Report |
| OneTime | One-Time | Setup items (formation, EIN, BOI, bank account, etc.) |

Additional features beyond the spreadsheet:
- Every status change is logged to a `filing_history` audit trail (who, when, from→to)
- Overdue / upcoming deadlines surfaced on the Dashboard
- Add / delete / edit rows directly in the UI
- "Generate next year's filings" bulk-adds a year's quarterly and annual rows

---

## Tech stack

| Layer | Tool |
|---|---|
| Database | **Firebase Firestore** (NoSQL, free Spark plan) |
| Auth | **Firebase Authentication** (email + password) |
| Backend | **firebase-admin** Python SDK (server-side Firestore, bypasses security rules) |
| Client auth | Firebase Auth REST API (via `requests` — no extra library needed) |
| UI | Streamlit (new page in existing toolbox) |

---

## Firestore collections

### `filings` (one document per filing instance)

```
filings/{doc_id}
  category          string     "quarterly" | "annual" | "one_time"
  filing_type       string     e.g. "NJ Sales Tax Return"
  jurisdiction      string     "New Jersey" | "Federal" | "N/A"
  year              int|null   e.g. 2026
  period            string     "Q2 2026" | "2026" | "" (one-time)
  quarter           string     "Q2 (May-Jun)" | null
  due_date          timestamp  filing deadline
  status            string     "Pending" | "Done" | "Overdue"
  date_filed        timestamp  null until marked done
  confirmation_number string   null or confirmation/ref number
  assigned_to       string     "LLC" | "Kadiatu" | "Emmanuel"
  notes             string     free-text notes
  created_at        timestamp  server timestamp
  updated_at        timestamp  server timestamp (updated on every save)
  updated_by        string     email of last editor
```

Document IDs are deterministic slugs derived from key fields so re-running the
seed script never creates duplicates:
- Quarterly: `q_{year}_{filing_type_slug}_{quarter_slug}_{assigned_to}`
- Annual:    `a_{year}_{filing_slug}_{assigned_to}`
- One-time:  `ot_{item_slug}`

### `filing_history` (append-only audit log)

```
filing_history/{auto_id}
  filing_id         string     document ID from filings collection
  changed_by        string     user email
  old_status        string     previous status value
  new_status        string     new status value
  note              string     optional freetext at time of change
  changed_at        timestamp  server timestamp
```

---

## Environment variables

Add these to your `.env` file (local) and to Streamlit Cloud Secrets (deployed).

```
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_WEB_API_KEY=your-web-api-key
FIREBASE_SERVICE_ACCOUNT=service_account.json
```

`service_account.json` is already in `.gitignore` — never commit it.

---

## Step-by-step Firebase setup

### 1 — Create the Firebase project

1. Go to **https://console.firebase.google.com**
2. Click **"Create a project"**
3. Project name: `centralline-compliance` (or any name)
4. Disable Google Analytics (not needed)
5. Click **"Create project"** → wait ~30 seconds → click **"Continue"**

---

### 2 — Enable Firestore Database

1. In the left sidebar click **"Build" → "Firestore Database"**
2. Click **"Create database"**
3. Choose **"Start in production mode"** (we use the Admin SDK server-side, so client rules don't matter — production mode is safer)
4. Location: **`us-east1`** (closest to New Jersey)
5. Click **"Enable"** — wait ~30 seconds

**Set security rules** (locks out direct client access; Admin SDK bypasses these):
- Click the **"Rules"** tab
- Replace the content with:
  ```
  rules_version = '2';
  service cloud.firestore {
    match /databases/{database}/documents {
      match /{document=**} {
        allow read, write: if false;
      }
    }
  }
  ```
- Click **"Publish"**

---

### 3 — Enable Authentication

1. In the left sidebar click **"Build" → "Authentication"**
2. Click **"Get started"**
3. Under **"Sign-in method"**, click **"Email/Password"**
4. Toggle the first switch **"Email/Password"** to **Enabled**
5. Leave "Email link (passwordless sign-in)" disabled
6. Click **"Save"**

---

### 4 — Create user accounts

1. Click the **"Users"** tab
2. Click **"Add user"**
3. Enter Kadiatu's email and a password → click **"Add user"**
4. Click **"Add user"** again
5. Enter Emmanuel's email and a password → click **"Add user"**

> You can reset passwords at any time from this screen. Users can also reset
> their own passwords via the "Forgot password" flow (future feature).

---

### 5 — Get the Service Account key

The service account lets the Python backend write to Firestore without going
through security rules.

1. Click the **gear icon** (top-left) → **"Project settings"**
2. Click the **"Service accounts"** tab
3. Click **"Generate new private key"** → **"Generate key"**
4. A JSON file downloads automatically
5. Rename it to **`service_account.json`**
6. Move it to the **root of this repo** (same folder as `pyproject.toml`)

It is already listed in `.gitignore`. Confirm it does NOT appear in `git status`.

---

### 6 — Get the Web API Key

The Web API Key is used to authenticate end-users (email + password sign-in).

1. Still in **"Project settings"** → click the **"General"** tab
2. Scroll to **"Your apps"** — if empty, click **"Add app" → Web (`</>`)**, give it
   a nickname like `centralline-web`, click **"Register app"**, then **"Continue"**
3. Back on the General tab, scroll to the Web app card
4. Copy the **"Web API Key"** (also shown as `apiKey` in the config snippet)

---

### 7 — Set environment variables

Create or update **`.env`** in the repo root:

```
FIREBASE_PROJECT_ID=centralline-compliance        # from Project settings → General
FIREBASE_WEB_API_KEY=AIzaSy...                    # from step 6
FIREBASE_SERVICE_ACCOUNT=service_account.json     # path to the JSON from step 5
```

For **Streamlit Cloud** (when deployed):
1. Go to your app at share.streamlit.io
2. Click **⋮ → Settings → Secrets**
3. Add:
   ```toml
   FIREBASE_PROJECT_ID = "centralline-compliance"
   FIREBASE_WEB_API_KEY = "AIzaSy..."
   FIREBASE_SERVICE_ACCOUNT_JSON = """
   { ... paste the entire contents of service_account.json here ... }
   """
   ```
   Note: on Streamlit Cloud we paste the JSON content directly (can't upload a file),
   so the app reads it from the env var `FIREBASE_SERVICE_ACCOUNT_JSON` instead of a
   file. The `firebase_client.py` handles both cases automatically.

---

### 8 — Install new dependencies

```bash
source venv311/bin/activate
pip install firebase-admin openpyxl
pip freeze | grep -E "firebase|openpyxl" >> requirements.txt   # handled by pyproject
```

Or just:
```bash
pip install -e ".[dev]"
```

(firebase-admin and openpyxl have been added to `pyproject.toml`.)

---

### 9 — Run the seed script

```bash
python scripts/seed_compliance.py \
    /path/to/CentralLineGroup_Compliance_Tracker.xlsx \
    --service-account service_account.json
```

The script reads all three sheets (Quarterly, Annual, OneTime) and upserts
every row into the `filings` collection. Safe to re-run — existing documents
are updated in place, new rows are added.

Preview without writing:
```bash
python scripts/seed_compliance.py \
    /path/to/CentralLineGroup_Compliance_Tracker.xlsx \
    --dry-run
```

---

### 10 — Run the app locally

```bash
streamlit run src/sa_rebuild/web/app.py
```

Navigate to **"LLC Compliance"** in the sidebar. Sign in with one of the user
accounts created in step 4. The compliance tracker will load data from Firestore.

---

## Project layout (compliance-related files)

```
scripts/
└── seed_compliance.py          One-time + re-runnable Excel → Firestore import

src/sa_rebuild/
└── compliance/
    ├── __init__.py
    ├── firebase_client.py      Cached Firestore client (Admin SDK)
    ├── auth.py                 Email/password sign-in via Firebase Auth REST API
    └── db.py                   CRUD helpers (get, update, add, delete, history)

src/sa_rebuild/web/
├── app.py                      Navigation (now includes LLC Compliance entry)
└── pages/
    └── 2_LLC_Compliance.py     Full Streamlit page
```

---

## What is already implemented (this branch)

- [x] Seed script (`scripts/seed_compliance.py`)
- [x] Firebase client module with Streamlit cache and Cloud Secrets support
- [x] Auth module (email/password via REST API, sign-out)
- [x] DB module (get filings, update, add, delete, audit history)
- [x] Full compliance page UI — Dashboard, Quarterly, Annual, One-Time tabs
- [x] Navigation entry added to `app.py`
- [x] Dependencies added to `pyproject.toml` and `requirements.txt`

## What the user needs to do

- [ ] Create Firebase project (steps 1–6 above)
- [ ] Add env vars to `.env` and Streamlit Cloud Secrets (steps 7, Cloud note)
- [ ] Run seed script once to import existing Excel data (step 9)
- [ ] Create user accounts in Firebase Auth (step 4)
