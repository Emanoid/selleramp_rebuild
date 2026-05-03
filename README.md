# CentralLine Sourcing Toolbox

Internal tools for Central Line Group LLC — Amazon FBA sourcing and business compliance.

**Live app:** [centralline-tools.streamlit.app](https://centralline-tools.streamlit.app)

> **Version history**
> `0.x.x` — desktop app era (macOS .app / Windows .exe, archived on `os_based_build`)
> `1.x.x` — web app era (Streamlit Community Cloud, deployed from `main`)

---

## Table of Contents

- [Keepa Search Tool](#-fba-calculator)
  - [What it does](#what-it-does)
  - [For users](#for-users)
  - [For developers](#for-developers)
- [LLC Compliance Tracker](#-llc-compliance-tracker)
  - [What it does](#what-it-does-1)
  - [For users](#for-users-1)
  - [For developers](#for-developers-1)
- [Keepa SellerAmp Compare](#-keepa-selleramp-compare)
  - [What it does](#what-it-does-2)
  - [For users](#for-users-2)
  - [For developers](#for-developers-2)
- [Finance Tracker](#-finance-tracker)
  - [What it does](#what-it-does-3)
  - [For users](#for-users-3)
  - [For developers](#for-developers-3)
- [Known Limitations](#known-limitations)

---

## 🧮 Keepa Search Tool

### What it does

Upload a CSV of UPCs or ASINs with your wholesale cost. The calculator fetches live Amazon data via your Keepa Pro key and returns a per-row **Buy / Caution / Skip** verdict — recommended sell price, all Amazon fees, profit, ROI, monthly sales estimate, competition diagnostics, and a direct listing link.

---

### For users

#### Step 1 — Get your Keepa API key

1. Sign in at [keepa.com](https://keepa.com).
2. Go to **API access** in the top menu.
3. Copy your **Private API access key** — it looks like a long string of letters and numbers.

#### Step 2 — Prepare your spreadsheet

Download the template inside the app using the **"Download CSV template"** button, then fill it in. Save it as a `.csv` file before uploading.

| Column | Required? | Notes |
|---|---|---|
| `upc` | One of `upc` / `asin` | 12-digit barcode on the product |
| `asin` | One of `upc` / `asin` | Amazon's 10-character identifier (starts with B) |
| `cost` | Yes | Your wholesale cost per unit in USD |
| `weight_lbs` | No | Overrides Keepa's package weight if you know the exact weight |
| `prep_cost` | No | Extra prep cost per unit — defaults to $0 |

> **Excel tip:** format the `upc` column as **Plain Text** before pasting barcodes — Excel automatically converts long numbers to scientific notation (`8.83503E+11`), which breaks the lookup.

#### Step 3 — Run an analysis

1. Open the app and select **Keepa Search Tool** in the sidebar.
2. Paste your Keepa API key into the **"Keepa API key"** box in the left sidebar.
3. Upload your CSV and click **Start run**.
4. Watch live progress — results appear row by row. Each row takes roughly 7–8 minutes at steady state because Keepa limits how fast data can be fetched (see [Token reality](#token-reality) below).
5. Click **Download report** when the run finishes. The report is a CSV you can open in Excel.

#### Step 4 — Runs are self-managing

Once you click **Start run**, the app runs autonomously until every row is done. You do not need to babysit it.

**What the app handles automatically, without any clicks:**

| Situation | What happens |
|---|---|
| Keepa token bucket depleted | Worker sleeps the exact time needed for tokens to refill, then continues |
| Token count drift (NOT_ENOUGH_TOKEN) | Resets local count to 0, backs off 60 s → 120 s → … (up to 10 attempts) |
| Network / API error on a row | Retries up to 5 times with backoff (30 s → 60 s → …), then skips that row |
| Streamlit server restart | App auto-resumes the interrupted run on the next browser open — no click needed |
| Opening the app in a different browser | Same Firestore state — you see the same run, can track it live, download partial results |

**When a click IS needed:**

| Situation | What to do |
|---|---|
| You clicked ⏹ Stop yourself | Click **▶ Resume previous run** or open the run in History → Track → Resume here |
| Keepa API key missing after a restart | Enter the key in the sidebar — the banner tells you this |
| Token drift retries exhausted (10 consecutive drift errors) | Click Resume — extremely rare; indicates the Keepa token mirror is severely out of sync |

#### Token reality

Your Keepa Pro account has a **60-token bucket** that refills at **1 token per minute**. A full product lookup costs roughly 6–8 tokens, so:

| Scenario | Rate |
|---|---|
| Burst (fresh bucket) | ~7–10 products in a row before hitting the limit |
| Steady state | ~1 product every 7–8 minutes |
| 100-row CSV | ~11–13 hours total wall time |
| Re-running a UPC you ran before | 0 tokens (24-hour cache) |

**Token drift auto-retry:** If Keepa rejects a call because its internal count disagrees with the local mirror ("NOT_ENOUGH_TOKEN"), the app resets the local count to 0 and backs off: 60 s, 120 s, 240 s … up to 10 attempts (15-min cap per attempt). The log shows each retry live. After 10 consecutive drift failures the run pauses and asks you to resume — this is extremely rare.

**Token depletion (ordinary):** When the bucket is empty and the predicted wait is long, the runner sleeps the exact required duration, emitting a live countdown in the log every 30 seconds, then retries without any user action.

#### Understanding the results

| Column | What it means |
|---|---|
| `viability_label` | One-glance verdict: **Buy**, **Caution**, or **Skip** with a reason |
| `recommended_sell_price` | Calculated safe sell price (see rule below) |
| `estimated_profit` | Sell price minus all costs: your cost + Amazon fees + inbound shipping + prep |
| `roi_pct` | Return on investment as a percentage |
| `monthly_sales` | Estimated units sold per month for this product |
| `bsr` / `bsr_pct` | Amazon Best Seller Rank and rank as a % of its category |
| `live_fba_seller_count` | Number of FBA-New sellers currently on the listing |
| `amazon_dominant` | True if Amazon held the buy box ≥ 70% of the last 90 days |
| `storefront_url` | Click to open the Amazon listing |
| `current_buy_box` | Buy-box price at the moment of the run |
| `buy_box_30d_avg` | 30-day time-weighted average buy-box price |

**Verdict meanings:**

| Label | What it means |
|---|---|
| `Buy` | Profit ≥ $1, ROI ≥ 30%, not dominated, BSR in top 2% of category, ≤ 15 FBA sellers |
| `Caution — thin margin` | Profitable but below the profit or ROI threshold |
| `Caution — crowded` | Profitable but too many FBA sellers on the listing |
| `Skip — Sell price below cost` | The market price is below what you paid |
| `Skip — Amazon dominant` | Amazon is winning the buy box — nearly impossible to compete |
| `Skip — Brand dominant (heuristic)` | A single brand-matching seller controls the buy box |
| `Skip — Slow seller` | BSR is outside the top 2% — moves too slowly |
| `Pass` | Profitable but below all viability thresholds |

---

### For developers

#### General setup

```bash
git clone https://github.com/Emanoid/selleramp_rebuild.git
cd selleramp_rebuild
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

#### Environment variables

Add to `.env` at the project root:

```
KEEPA_API_KEY=your_keepa_key_here
FIREBASE_SERVICE_ACCOUNT=service_account.json
FIREBASE_WEB_API_KEY=your-web-api-key-here
```

`SA_REBUILD_HOME` optionally overrides the local data folder (cache, state, output). Default: `~/.sa-rebuild/`.

The Keepa Search Tool uses Firestore (via the same Firebase project as the LLC tool) to persist run state and output rows across Streamlit server restarts. Locally, if Firebase is configured it uses Firestore; the CLI (`sa-rebuild run`) uses disk state regardless.

#### Running locally

```bash
streamlit run src/sa_rebuild/web/app.py
```

#### Running the tests

```bash
pytest -q
```

43 offline tests — no API key required. All Keepa responses are mocked.

#### Deploying to Streamlit Community Cloud

1. Push the branch to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**.
3. Repo: `Emanoid/selleramp_rebuild`, branch: `main`, file: `src/sa_rebuild/web/app.py`.
4. Under **Settings → Secrets**, add all of the following:

```toml
KEEPA_API_KEY = "your_keepa_key"
FIREBASE_WEB_API_KEY = "your-web-api-key"
FIREBASE_SERVICE_ACCOUNT_JSON = '''{"type":"service_account",...full minified JSON...}'''
```

5. Click **Deploy**.

> Minify the service account JSON: `python -c "import json,sys; print(json.dumps(json.load(open('service_account.json'))))"`.

The Keepa Search Tool stores all run state and output rows in Firestore (`fba_runs` and `fba_output` collections), so data survives Streamlit server restarts. The Run History panel and Clear History button in the UI manage these collections directly.

#### Code layout — Keepa Search Tool

```
src/sa_rebuild/
├── config.py                   # AppConfig (Pydantic settings) — shared by both tools
├── paths.py                    # Runtime data dirs (cache, state, output) — shared
├── web/
│   ├── app.py                  # Entry point — navigation wirer
│   ├── home.py                 # Landing page (two-column tool cards)
│   └── pages/
│       └── 1_Keepa_Search_Tool.py # Keepa sourcing tool UI
└── fba/                        # All Keepa Search Tool source code
    ├── runner.py               # Per-row Keepa processing + token wait + retry logic
    ├── keepa_client.py         # Token-aware Keepa wrapper + 24h cache + drift retry
    ├── keepa_data.py           # Keepa response field extraction helpers
    ├── cloud_state.py          # Firestore-backed run state (used by deployed app)
    ├── state.py                # Disk-backed run state (used by CLI)
    ├── csv_io.py               # Input CSV parsing + append-on-row output
    ├── report.py               # Assembles the final per-UPC output row
    ├── cache.py                # SQLite TTL cache
    ├── token_bucket.py         # Local Keepa token mirror
    └── analytics/
        ├── pricing.py          # Recommended sell price rule
        ├── competition.py      # Dominance scoring (Amazon + brand)
        ├── sales.py            # Monthly sales + BSR percentile
        ├── fees.py             # Referral + FBA + inbound fee tables
        ├── variations.py       # Sibling / variation viability
        └── viability.py        # Buy / Caution / Skip label logic
config.yaml                     # Tunable thresholds (ROI, BSR%, seller count, etc.)
tests/                          # 43 offline tests — no API key required
```

#### Recommended sell price rule

1. Anchor on the **30-day buy-box average** (`buy_box_30d_avg`).
2. If the average is below the current buy-box price (market spiked up) → use `mean(avg30, current_bb)` to price conservatively.
3. If the average is at or above the current price (market stable or dipping) → use `avg30` directly.
4. If there is no buy-box history → fall back to the lowest current live FBA listing.

#### Full output column reference

| Column | What it means |
|---|---|
| `upc`, `asin`, `title`, `brand` | Identifiers and product name |
| `category_root`, `category_leaf` | Top-level and most-specific Amazon category |
| `is_variation`, `variation_count` | True + sibling count when this ASIN is a variation child |
| `viable_variations` | Siblings with buy box ≥ rec price and seller count < threshold |
| `cost`, `weight_lbs`, `inbound_cost`, `prep_cost` | Your inputs + derived inbound shipping cost |
| `current_lowest_fba_new` | Cheapest live FBA-New offer at time of run |
| `current_buy_box` | Buy-box price at time of run |
| `buy_box_30d_avg` | Time-weighted mean buy-box price over last 30 days |
| `buy_box_volatility_cv` | stddev / mean over last 90 days — below 0.05 is stable |
| `recommended_sell_price` | Calculated safe sell price (see rule above) |
| `referral_fee`, `fba_fulfillment_fee`, `misc_fee`, `total_fees` | Amazon-side fees breakdown |
| `estimated_profit`, `roi_pct` | Net profit and ROI after all fees, cost, inbound, prep |
| `monthly_sales` | Estimated units/month for this ASIN |
| `bsr`, `bsr_pct` | Current rank + rank as % of leaf category size |
| `live_fba_seller_count`, `live_fbm_seller_count` | Currently-live seller counts by fulfillment type |
| `amazon_buybox_share_pct`, `amazon_dominant`, `brand_dominant` | Competition diagnostics |
| `storefront_url` | Direct link to the Amazon listing |
| `viability_label` | One-glance verdict |
| `notes` | Free-text caveats (e.g. why a Skip was triggered) |

---

## 📋 LLC Compliance Tracker

### What it does

Live replacement for the Excel compliance tracker. Tracks every quarterly, annual, and one-time filing requirement for Central Line Group LLC — with login-gated access, a full status-change audit trail, CSV import/export, and row reordering.

| Tab | What it does |
|---|---|
| Dashboard | Overdue filings and next 5 upcoming deadlines at a glance; full filing quick-reference table |
| Quarterly | NJ Sales Tax, Federal/NJ estimated tax — filter by year, quarter, assignee, status |
| Annual | Form 1065, NJ-1065, personal 1040s — filter by year, assignee, status |
| One-Time | Setup items (bank account, Amazon seller account, BOI report, LLC formation, etc.) |
| Settings | Edit company name / formation date; manage member list; sync assignees from filings |

---

### For users

#### Signing in

1. Open the app and select **LLC Compliance** in the sidebar.
2. Sign in with your email and password. Accounts are created by the admin in Firebase Console → Authentication — you cannot self-register.
3. To sign out, click **Sign out** in the left sidebar at any time.

#### Dashboard

The dashboard loads automatically on sign-in. It shows:
- **Overdue** — any filing whose due date has passed and status is not Done.
- **Coming up next** — the 5 nearest upcoming deadlines, with days remaining.
- **Filing Quick Reference** — a static table of all recurring filing types, who files them, and their typical deadlines.

#### Editing a filing

1. Go to the relevant tab (**Quarterly**, **Annual**, or **One-Time**).
2. Click the checkbox on the left of the row you want to edit.
3. Click **Edit**. A dialog opens with all fields for that filing.
4. Update **Status**, **Date Filed**, **Notes**, or any other field.
5. Click **Save**. Every status change is logged automatically with a timestamp and your email — click **History** on a selected row to see the full log.

#### Filtering the table

The default view hides rows marked **Done** — only Pending and Overdue rows are shown. Use the filter bar above the table to:
- Show Done rows — add "Done" to the Status filter.
- Narrow by year, quarter, or assignee.
- Click **✖ Clear filters** to reset everything back to defaults.

#### Adding a filing

Click **+ Add** in the action bar above the table. Fill in the filing type, jurisdiction, due date, and assignee, then click **Add**. Newly added rows are marked **New** in the first column until you navigate away.

#### Deleting a filing

Select one or more rows (using the checkboxes), then click **Delete (n)**. A confirmation dialog lists the rows to be deleted — click **Yes, delete** to confirm. Deletions are permanent.

#### Importing filings from a spreadsheet

1. Click **Download CSV template** to get a pre-formatted CSV for that tab.
2. Fill in the template — each column is described in the header row.
3. Click **Import from CSV**, then upload your filled file.
4. A preview appears — review it, then click **Import n row(s)** to write the rows to the database.

#### Reordering rows

Select a row and click **↑ Up** or **↓ Down** in the action bar. The new order is saved to the database immediately and persists across all sessions.

#### Tracking confirmation numbers

The **One-Time** tab has a **Confirmation #** field in the Edit dialog. Use it to record reference numbers from completed filings.

#### Settings tab — managing members

The **Members** list controls every "Assigned To" dropdown throughout the app.

- **Add a member** — type a name in the **Add member** form and click **Add**.
- **Sync from filings** — click **Sync now** to automatically scan all existing filings and add any assignee name not yet in the list.
- **Remove a member** — click **Remove** next to their name. If any filings are assigned to them, you must reassign those filings (to an existing member or a new name) before the removal is confirmed. Filings are updated in the database immediately.

#### Settings tab — company info

Edit the company name and formation date shown in the page header. Click **Save** to apply.

---

### For developers

#### General setup

```bash
git clone https://github.com/Emanoid/selleramp_rebuild.git
cd selleramp_rebuild
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

#### Environment variables

Add to `.env` at the project root:

```
FIREBASE_PROJECT_ID=your-project-id-here
FIREBASE_WEB_API_KEY=your-web-api-key-here
FIREBASE_SERVICE_ACCOUNT=service_account.json
```

Drop `service_account.json` (downloaded from Firebase Console → Project Settings → Service Accounts → Generate new private key) into the repo root. It is `.gitignore`'d — never commit it.

For Streamlit Cloud, use `FIREBASE_SERVICE_ACCOUNT_JSON` instead (see Deployment below).

#### Running locally

```bash
streamlit run src/sa_rebuild/web/app.py
```

#### Seeding Firestore from the Excel tracker

```bash
python scripts/seed_compliance.py path/to/CentralLineGroup_Compliance_Tracker.xlsx
```

Options:

| Flag | What it does |
|---|---|
| `--dry-run` | Print what would be written without touching Firestore |
| `--wipe` | Delete all documents in the `filings` collection before seeding |
| `--service-account PATH` | Path to service account JSON (default: `service_account.json`) |

Re-running is safe — rows are upserted by deterministic document IDs. Structural fields (filing type, jurisdiction, year, quarter) are updated; status, notes, date filed, and confirmation number are preserved from whatever is already in Firestore.

#### Deploying to Streamlit Community Cloud

1. Push the branch to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**.
3. Repo: `Emanoid/selleramp_rebuild`, branch: `main`, file: `src/sa_rebuild/web/app.py`.
4. Under **Settings → Secrets**, paste the following (use triple single-quotes for the JSON so `\n` in the private key is preserved):

```toml
FIREBASE_PROJECT_ID = "your-project-id"
FIREBASE_WEB_API_KEY = "your-web-api-key"
FIREBASE_SERVICE_ACCOUNT_JSON = '''{"type":"service_account","project_id":"...full minified JSON on one line..."}'''
```

5. Click **Deploy**.

> The JSON must be on a **single line** inside the triple-quotes. Export it with `python -c "import json,sys; print(json.dumps(json.load(open('service_account.json'))))"` to produce the minified version.

**Never commit:** `service_account.json`, `streamlit_secrets.toml`, `.streamlit/secrets.toml` — all in `.gitignore`.

#### Firebase project setup

| Step | What to do |
|---|---|
| 1 | Create a Firebase project at [console.firebase.google.com](https://console.firebase.google.com) |
| 2 | Enable **Firestore Database** (us-east1, production mode) |
| 3 | Enable **Authentication** → Email/Password sign-in method |
| 4 | Create a user account for each member in Authentication → Users |
| 5 | Generate a service account key: Project Settings → Service Accounts → Generate new private key |
| 6 | Copy the Web API Key from Project Settings → General |

#### Firestore collections

**LLC Compliance Tracker:**

| Collection | Document shape |
|---|---|
| `filings` | `category`, `filing_type`, `jurisdiction`, `year`, `quarter`, `period`, `due_date`, `status`, `date_filed`, `confirmation_number`, `assigned_to`, `notes`, `order`, `created_at`, `updated_at`, `updated_by` |
| `filing_history` | `filing_id`, `old_status`, `new_status`, `changed_by`, `note`, `changed_at` — one doc per status change |
| `members` | `name` — one doc per assignable person |
| `config/company` | `name`, `formed` — single document |

**Keepa Search Tool:**

| Collection | Document shape |
|---|---|
| `fba_runs/{run_id}` | `run_id`, `status`, `rows_total`, `rows_done`, `remaining_row_ids`, `completed_row_ids`, `input_rows` (serialised InputRow list), `errors`, `last_heartbeat`, `started_at`, `last_updated_at` |
| `fba_output/{run_id}__{row_id}` | All report columns + `run_id`, `row_id` — one doc per completed row |

`fba_runs` requires a Firestore index on `started_at` (descending). Firestore will log a link to create it automatically the first time the history query runs — click it once. The **Clear all FBA history** button in the UI wipes both collections.

#### Code layout — LLC Compliance Tracker

```
src/sa_rebuild/
├── config.py                   # AppConfig (Pydantic settings) — shared by both tools
├── paths.py                    # Runtime data dirs — shared
├── web/
│   ├── app.py                  # Entry point — navigation wirer
│   └── pages/
│       └── 2_LLC_Compliance.py # All compliance UI — tabs, dialogs, filters, action bar
└── compliance/                 # All LLC Compliance Tracker source code
    ├── firebase_client.py      # Cached Firestore client (st.cache_resource)
    │                           #   reads FIREBASE_SERVICE_ACCOUNT_JSON or local file
    ├── auth.py                 # Firebase Auth REST API — email/password sign-in
    └── db.py                   # All Firestore CRUD:
                                #   get_filings / get_all_filings / get_filing_history
                                #   add_filing / update_filing / delete_filing
                                #   ensure_order / move_rows (row reordering)
                                #   get_members / get_members_with_ids
                                #   add_member / delete_member
                                #   count_filings_by_assignee / reassign_filings
                                #   get_company_info / save_company_info
                                #   sync_members_from_filings
scripts/
└── seed_compliance.py          # Excel → Firestore (filings + members, idempotent)
```

#### Key architectural notes

- **No module-level db imports** — all `from sa_rebuild.compliance.db import ...` calls are lazy (inside the function that uses them). This avoids import-time failures on Streamlit Cloud before the environment is fully initialised.
- **`-e .` in requirements.txt** — the local package is installed as an editable install on Cloud. This ensures `import sa_rebuild` always resolves to the current source, not a stale cached module.
- **`@st.cache_resource` on `get_db()`** — the Firestore client is initialised once per process and shared across all user sessions.
- **Row ordering** — the `order` field is an integer stored on each Firestore document. `ensure_order()` lazily migrates any doc missing this field. `move_rows()` rotates order values between adjacent documents without renumbering the whole collection.
- **Audit trail** — `update_filing()` writes a `filing_history` document whenever the `status` field changes, capturing old value, new value, who changed it, and a timestamp.

---

## Keepa Search Tool — Full Behavior Reference

### Run lifecycle

```
Upload CSV → Start run → [processing loop] → Finished
                              ↕ auto
                         Token wait (sleep)
                         Drift retry (backoff)
                         Network retry (backoff)
                         Server restart (auto-resume)
```

Every completed row is immediately written to Firestore (`fba_output`). Run state (which rows remain) is updated after each row in `fba_runs`. Both survive server restarts.

### Run statuses

| Status | Meaning | Auto-recovers? |
|---|---|---|
| `pending` | Created, worker not yet started | Yes — worker starts on launch |
| `running` + fresh heartbeat | Worker active and posting heartbeats every 10 s | — |
| `running` + stale heartbeat (>30 s) | **Orphaned** — server restarted mid-run | Yes — auto-resumes on next page open |
| `paused` | Manually stopped by user | No — click Resume |
| `finished` | All rows done | — |
| `cancelled` | Terminated via Terminate button | No |

### Orphaned runs

When Streamlit Community Cloud restarts the server (happens automatically after inactivity, memory pressure, or code deploys), the worker thread dies but Firestore state is intact. The run shows as `running` in history but its heartbeat goes stale.

On the **next browser open** (any browser, any device):
1. The app loads and queries Firestore for the most recent run
2. If `status=running` and `last_heartbeat > 30 s` old → detected as orphaned
3. A banner appears: "Server restart detected — auto-resuming…"
4. The worker restarts immediately (if the Keepa key is in the sidebar)
5. Processing continues from the first unfinished row
6. The live log shows the recovery starting in real time

You do not need to do anything. Just keep the browser tab open.

### Live log

The log panel (always expanded during runs) shows every event newest-first:

| Prefix | What it means |
|---|---|
| `→ row#N …` | Starting fetch for this row |
| `· [time] ·` | Informational event (wait tick, retry countdown, etc.) |
| `⏳ row#N: token sleep — Xm Ys remaining` | Token refill in progress, updates every 30 s |
| `⡿ row#N: drift backoff …` | NOT_ENOUGH_TOKEN detected, exponential backoff in progress |
| `🌐 row#N: network retry …` | Network error, countdown to retry |
| `✓ row#N → Buy/Caution/Skip …` | Row completed successfully |
| `✗ row#N … skipping row` | Row permanently skipped after 5 network retries |
| `⏸ Stopped by user` | Manual stop |
| `★ Run complete` | All rows finished |

During a token wait the log updates every 30 seconds. During backoffs it updates every 15 seconds. You always see what the runner is doing.

### Run History panel

Always visible below the progress section. Shows all runs from Firestore, newest first.

| Button | What it does |
|---|---|
| 🔍 Track | Attaches this browser to that run's live progress. Auto-refreshes from Firestore every 3 s. |
| ✕ Untrack | Detaches — returns to showing your current session's run (if any) |
| 📥 Download | Assembles completed rows from Firestore into a CSV — works even mid-run |
| ⏹ Terminate | Sets `status=cancelled` in Firestore; active worker sees it within 5 s and stops |
| 🗑 Delete | Removes the run document and all its output rows from Firestore |

**Track** is cross-browser: start a run on your laptop, open the app on your phone, click Track on that run — you see live progress from Firestore refreshing every 3 seconds.

### Firestore data volume

A 1500-row run writes:
- 1 document to `fba_runs` (~5 KB including input row list)
- 1500 documents to `fba_output` (~2 KB each → ~3 MB total)
- ~150 partial updates to `fba_runs` (heartbeats + per-row progress)

Use the **Clear all FBA history** button in the Danger Zone after downloading your report.

---

## FAQ

**Q: I closed my browser tab mid-run. Did I lose everything?**
A: No. The worker thread lives in Streamlit's server process, not the browser. Closing the tab doesn't kill it. Open the tab again — you'll see the run still progressing.

**Q: The Streamlit server restarted and the run disappeared. What do I do?**
A: Just open the app. It detects the orphaned run automatically and resumes. You should see a yellow banner within 5 seconds of the page loading.

**Q: I see "orphaned" next to a run in history. Should I click anything?**
A: No. "Orphaned" means the server restarted and the run needs to be picked back up. It will auto-resume the moment any browser opens the app. If you want to watch it recover, click 🔍 Track.

**Q: The log shows "⏳ token sleep — 7m 30s remaining". Is the app broken?**
A: No. Keepa's token bucket is empty and the runner is sleeping until it refills. This is expected — your plan refills at 1 token/minute, each row costs ~8 tokens. The log updates every 30 seconds so you can see it counting down. The run continues automatically when the wait is over.

**Q: What does "token count drift" mean?**
A: The app tracks how many Keepa tokens you have locally. Sometimes Keepa's internal count disagrees (usually by 1–2 tokens). The app resets its count to 0 and backs off before retrying. You'll see `⡿ drift backoff` in the log. No action needed.

**Q: A row shows "skipping row" in the log. What happened?**
A: Keepa returned a network error 5 times in a row for that specific product. The row is marked as an error and the run continues with the next row. Errors are listed in the History panel. You can re-run just that row manually by creating a 1-row CSV with the same UPC/ASIN.

**Q: Can I download results before the run is finished?**
A: Yes. Click 📥 Download in the progress section or in History at any time. The CSV contains only the rows that have completed so far.

**Q: I started a run on one device and want to see it on another.**
A: Open the app on the second device, scroll to Run History, and click 🔍 Track on the active run. It refreshes every 3 seconds from Firestore.

**Q: Can I run two batches at once?**
A: Not in the same browser session — a session can only have one active worker. To run two truly parallel batches you'd need two Keepa accounts (they share the same 60-token bucket, so parallel runs from the same account compete for tokens and can cause drift errors).

**Q: Why does my run take so long?**
A: At 1 token/min refill and ~8 tokens/row, you process roughly 1 row every 8 minutes after the initial 60-token burst. A 100-row file takes ~13 hours; 1500 rows takes ~8 days. Items already in the 24-hour local cache are free (0 tokens). Running the same UPCs again within 24 hours is instant.

**Q: How do I clear old run data?**
A: Scroll to **Danger Zone** at the bottom of the page and click **Clear all FBA history**. This deletes all `fba_runs` and `fba_output` documents from Firestore. Download any reports you need first.

---

---

## 📊 Keepa SellerAmp Compare

### What it does

Upload your wholesale cost list and a Keepa Product Viewer export — no API key needed. The tool matches each product by UPC or ASIN, computes the recommended sell price, ROI, profit, and fee breakdown using the same logic as the Keepa Search Tool, and outputs a single comparison CSV with every Keepa price column, price-minus-cost diffs, and fee breakdowns side-by-side with your cost.

**Key differences from the Keepa Search Tool:**
- No API key or internet connection needed at run time — works entirely from a Keepa export file you download yourself.
- Instant results — no token waits, no background worker.
- Multiple ASINs per UPC: if one barcode maps to several Amazon listings, each becomes its own output row (sorted by how closely the product weight matches your input).

---

### For users

#### Step 1 — Export your products from Keepa

1. Sign in at [keepa.com](https://keepa.com).
2. Open **Product Viewer** from the top navigation bar.
3. In the search box, paste your UPCs, EANs, or ASINs — **comma separated** (e.g. `701619100159, 840187704557, B08N5WRWNW`).
4. Wait for the results table to finish loading (all rows should show price data).
5. Click **Export** (top-right of the results grid) and choose **Excel (.xlsx)** or **CSV**.

> The critical column Keepa exports is called **"Imported by Code"** — it stores whatever code you searched for (UPC, EAN, ASIN). This is the link between your wholesale list and the Keepa data. If this column is missing, the tool cannot match.

#### Step 2 — Prepare your cost list

Download the **CSV Template** from the app (Step 1 inside the tool) and fill it in.

| Column | Required? | Notes |
|---|---|---|
| `upc` | One of `upc` / `asin` | 12- or 14-digit barcode on the product |
| `asin` | One of `upc` / `asin` | Amazon's 10-character identifier (starts with B) |
| `cost` | Yes | Your wholesale cost per unit in USD |
| `weight_lbs` | Recommended | Used to disambiguate products when multiple ASINs share a UPC |

> **Excel tip:** format the `upc` column as **Plain Text** before pasting barcodes — Excel automatically converts long numbers to scientific notation (`8.83503E+11`), which breaks matching.

#### Step 3 — Upload and run

1. Open the app and select **Keepa SellerAmp Compare** in the sidebar.
2. Upload your cost CSV in the left upload box.
3. Upload your Keepa export (.xlsx or .csv) in the right upload box.
4. Click **▶ Run Comparison**.
5. Review the results table and use any of the four download buttons:
   - **⬇ Download Excel** — all rows, standard layout
   - **⬇ Download Excel (Transposed)** — all rows, fields as rows / products as columns
   - **⬇ Download CSV** — all rows, plain CSV
   - **✅ Download Recommended Only** — transposed Excel filtered to `Recommend` rows only

#### Understanding the results

The first columns are the most important:

| Column | What it means |
|---|---|
| `Investment Decision` | **Recommend** if profit ≥ $1 AND ROI ≥ 30%; otherwise **Not Recommend** |
| `Recommended Selling Price` | Calculated safe sell price (see rule below) |
| `ROI` | Return on investment as a percentage |
| `Estimated Profit` | Net profit after all fees, cost, and inbound shipping |
| `cost` | Your wholesale cost (from your input file) |

Then price columns (Buy Box first, then Amazon, then FBA New, then everything else), followed by diff columns (`Diff: Buy Box: Current` = buy-box price − your cost), fee breakdown, weights, and all remaining Keepa data.

**"No Match Found"** rows mean the UPC or ASIN wasn't found in your Keepa export — go back to Keepa and import that product, then re-export and re-run.

**Multiple rows for the same product** mean one UPC matches several Amazon ASINs (common for products sold in different configurations or by multiple brands). Each row is a different ASIN. They are sorted by how closely the Keepa package weight matches your input weight — the best physical match is first. Check `Weight Distance (lbs)` to see how close each match is.

#### Fee column reference

| Column | What it means |
|---|---|
| `Fee: Referral Fee` | Amazon's cut of the sale (typically 8–15% depending on category) |
| `Fee: FBA Pick&Pack` | Amazon's per-unit FBA fulfillment fee (pulled from Keepa, or estimated from weight) |
| `Fee: Sales Tax` | Sales tax rate (6.63%) applied to sell price |
| `Fee: Inbound Cost` | Your cost to ship the unit to an Amazon fulfillment center ($0.80/lb) |
| `Fee: Total Amazon Fees` | Referral + FBA + Sales Tax (everything Amazon takes before profit) |

---

### Recommended sell price — how it works

This section explains the exact pricing logic used to compute **Recommended Selling Price**.

#### For buyers / non-developers

The goal is to find a sell price that is competitive *without* chasing temporary price spikes.

Amazon buy-box prices move constantly. If you price at today's buy-box and the price drops tomorrow, you may be stuck with inventory you can't sell profitably. The algorithm anchors on the **30-day average** buy-box price, which smooths out day-to-day noise.

**The rule in plain English:**

1. **Start with the 30-day buy-box average.** This is the typical price over the past month — a more reliable signal than the current snapshot.
2. **If the current price is *higher* than the 30-day average** (the market just spiked), don't get greedy. Use the midpoint between the average and the current price. This means you still benefit from the elevated market, but you're not pricing at a peak that could disappear.
3. **If the current price is *at or below* the average** (the market is stable or dipped), use the 30-day average. Don't chase the dip.
4. **If there is no buy-box history at all**, fall back to the cheapest live FBA-New price on the listing. If that's also missing, use the cheapest New listing of any fulfillment type.

**Example:**

| Scenario | 30-day avg | Current BB | Recommended price |
|---|---|---|---|
| Market is stable | $22.00 | $21.50 | $22.00 (use avg) |
| Market just spiked | $22.00 | $26.00 | $24.00 (midpoint) |
| Only current data | — | $19.99 | $19.99 (current BB) |
| No buy-box at all | — | — | Cheapest FBA-New offer |

#### For developers

The algorithm is implemented in `src/keepa_compare/__main__.py → _rec_price()`, which mirrors `src/sa_rebuild/fba/analytics/pricing.py → recommended_sell_price()` exactly — but reads from Keepa export columns instead of the live Keepa API response.

```python
avg30  = "Buy Box: 90 days avg."   # Keepa export column
cur_bb = "Buy Box: Current"        # Keepa export column

if avg30 is not None and cur_bb is not None:
    if avg30 < cur_bb:
        return (avg30 + cur_bb) / 2  # market spiked — hedge to midpoint
    return avg30                     # stable or dipping — use avg

# Fallbacks (in order):
# 1. avg30 alone
# 2. cur_bb alone
# 3. New, 3rd Party FBA: Current
# 4. New: Current
```

**Why midpoint and not just avg30 when the market is up?**
Using the midpoint instead of avg30 lets you capture some of the elevated margin when the market moves in your favour, while preventing you from pricing at a spike that may revert before your unit sells. Using the current price outright would be too aggressive — you'd be racing for a price that may last hours.

---

### For developers

#### General setup

```bash
git clone https://github.com/Emanoid/selleramp_rebuild.git
cd selleramp_rebuild
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

#### Running locally

```bash
streamlit run src/sa_rebuild/web/app.py
```

The Keepa SellerAmp Compare page appears automatically as **page 3** in the sidebar.

#### Running from the CLI

```bash
python -m sa_rebuild.keepa_compare my_products.csv KeepaExport.xlsx
python -m sa_rebuild.keepa_compare my_products.csv KeepaExport.xlsx -o analysis.csv
```

No environment variables or API keys required.

#### Code layout

```
src/sa_rebuild/
├── keepa_compare/
│   ├── __init__.py           # empty — marks the package
│   └── __main__.py           # all logic + CLI entry point
│       ├── run_compare()         # public API — takes two Paths, returns DataFrame
│       ├── build_index()         # builds asin_idx and upc_idx from the Keepa export
│       ├── find_matches()        # matches one input row → list of Keepa row positions
│       ├── _rec_price()          # recommended sell price (mirrors pricing.py)
│       ├── _compute_fees()       # full fee breakdown (mirrors fees.py)
│       └── _build_row()          # assembles one output dict from input + Keepa row
└── web/pages/
    └── 3_Keepa_Compare.py    # Streamlit UI — template download, two uploads, run button
```

#### Matching logic

1. **ASIN input** — exact normalized match against the Keepa `ASIN` column. One input row → at most one output row.
2. **UPC input** — checked against:
   - `Imported by Code` (the code used to import the product into Keepa Product Viewer)
   - Every value in `Product Codes: UPC` (comma-separated; any single match qualifies)
   - Multiple matching ASINs → one output row per ASIN, sorted by weight distance ascending.
3. **Weight distance sort** — `abs(keepa_package_weight_lbs − input_weight_lbs)`. Keepa's `Package: Weight (g)` is used first; `Item: Weight (g)` is the fallback. Rows where Keepa has no weight data are sorted to the end (distance = 9999). This sort does not filter — all matching ASINs appear in the output.

#### Fee parameters

All fee constants are at the top of `__main__.py` and mirror `config.yaml`:

| Constant | Value | Source |
|---|---|---|
| `INBOUND_PER_LB` | $0.80 | SellerAmp profile: inbound per lb |
| `SALES_TAX_PCT` | 6.63% | SellerAmp profile: misc % (sales tax rate) |
| `REFERRAL_DEFAULT` | 15% | Used when Keepa's `Referral Fee %` column is empty |
| `MIN_PROFIT_USD` | $1.00 | Minimum profit to be "Recommend" |
| `MIN_ROI` | 30% | Minimum ROI to be "Recommend" |

The `Referral Fee %` and `FBA Pick&Pack Fee` Keepa export columns are used directly when present. If `FBA Pick&Pack Fee` is missing, the weight-based tier table in `_fba_fee_fallback()` is used.

#### Output column order

| Block | Columns |
|---|---|
| Decision | Investment Decision, Recommended Selling Price, ROI, Estimated Profit, cost |
| Prices | Buy Box → Amazon → FBA New → New → FBM → Prime Exclusive → Other new → Used tiers → Warehouse |
| Diffs | `Diff: <each price column>` = price − your cost |
| Fees | Referral Fee, FBA Pick&Pack, Sales Tax, Inbound Cost, Total Amazon Fees |
| Weights | Keepa Package Weight (g/lbs), Keepa Item Weight (g), Input Weight (lbs), Weight Distance (lbs) |
| Description | Title, Amazon URL, Matched ASIN |
| Identifiers | Input UPC, Input ASIN |
| All other Keepa columns | Every remaining column from the export, in original order |

---

---

## 💰 Finance Tracker

### What it does

Live replacement for `CentralLineGroup_Finance_Tracker.xlsx`. Tracks business expenses and Amazon income in Firestore with a full CRUD interface, then computes profit, tax reserve, reinvestment, and member distributions — all date-range-aware and recalculated live.

| Tab | What it does |
|---|---|
| Dashboard | Financial summary for any date range — revenue, expenses, profit, tax, reinvestment, and per-member share with % of revenue |
| Expenses | Log static and recurring expenses; built-in calculator totals any date range factoring in frequency and effective end dates |
| Amazon Income | Log deposit records; calculator shows net revenue and deposit count for any range |
| Amazon Profit | Date-range profit calculator — revenue and expenses auto-populate; editable tax rate, reinvest %, and member splits; save-as-defaults button |
| Settings | Configure OneDrive receipts path, income type dropdown options, and default profit parameters |

---

### For users

#### Signing in

1. Open the app and select **Finance Tracker** in the sidebar.
2. Sign in with your email and password (same Firebase account as LLC Compliance).
3. To sign out, click **Sign out** in the left sidebar.

#### Dashboard

Select a start and end date (default: last 12 months). The table updates live showing:
- Gross Revenue, Recurring Expenses, Static / One-time, Total Expenses, Pre-Tax Profit
- Tax Reserve, Reinvestment, Distributable Profit, per-member share
- Each row shows the dollar amount and its percentage of gross revenue.

#### Expenses tab

The **Expense Calculator** at the top computes:
- **Static Total** — sum of static expenses whose start date falls within the selected range.
- **Recurring Total** — for each recurring expense, clips the period to the selected range and multiplies by the appropriate unit (days / weeks / months / years).
- **All Total** — combined.

The table shows every expense with a computed **Total Spent** column (from start date to today or end date, whichever comes first).

**Recurring frequency behaviour:**
| Frequency | Calculation |
|---|---|
| Day | unit_price × number of days in range |
| Week | unit_price × days / 7 |
| Month | unit_price × inclusive month count |
| Year | unit_price × inclusive year count |
| Once | counted if start date falls in range |

#### Amazon Income tab

Add each Amazon payout as a record with date, type, and amount. The calculator sums net revenue and deposit count for any custom date range.

#### Amazon Profit tab

Set a date range. The tab auto-pulls:
- **Revenue** — income deposits whose date falls in the range.
- **Expenses** — expenses whose full period (start ≥ range start AND effective end ≤ range end) falls within the range.

Edit Tax Rate and Reinvest % inline — changes affect only this session until you click **Save as Defaults**. Member ownership percentages are editable here too. Click **↺ Reset to Defaults** to reload saved values.

#### Settings tab

- **Receipt Storage** — set the OneDrive folder URL or path. Shown as a hint in the Expenses add/edit dialog.
- **Income Types** — add or remove options in the Amazon Income Type dropdown.
- **Default Profit Settings** — edit member names, ownership percentages, default tax rate, and default reinvest %. These are the values the Amazon Profit tab loads on first visit each session.

---

### For developers

#### Firestore collections

| Collection | Document shape |
|---|---|
| `finance_expenses` | `type`, `item_description`, `unit_price`, `frequency`, `start_date`, `end_date`, `receipt_filename`, `notes`, `order`, `created_at`, `updated_at`, `updated_by` |
| `finance_income` | `date`, `type`, `amount`, `notes`, `order`, `created_at`, `updated_at`, `updated_by` |
| `finance_settings/finance_config` | `onedrive_receipts_path`, `income_types`, `members` (list of `{name, pct}`), `tax_rate`, `reinvest_pct` |

#### Code layout

```
src/sa_rebuild/
├── auth.py                        # Shared Firebase auth — sign_in() + login_wall()
│                                  #   used by both LLC Compliance and Finance Tracker
├── finance_tracker/
│   ├── __init__.py
│   └── db.py                      # All Firestore CRUD:
│                                  #   get/add/update/delete expenses and income
│                                  #   ensure_order / move_rows for both collections
│                                  #   get_settings / save_settings
└── web/pages/
    └── 4_Finance_Tracker.py       # All Finance Tracker UI — tabs, dialogs, calculators
```

#### Key architectural notes

- **Shared auth module** — `sa_rebuild.auth.login_wall(session_key, app_name)` is used by both LLC Compliance and Finance Tracker. Each app passes its own `session_key` so sessions are independent.
- **Calculator logic** — `_compute_expense_for_range()` clips each expense's effective period to `[calc_start, calc_end]` before computing. This matches the Excel SUMPRODUCT formula for the recurring total. The Profit tab uses `_compute_profit_expenses()` which matches the Excel formula exactly (start_date ≥ profit_start AND eff_end ≤ profit_end, using pre-computed total_spent).
- **Profit tab session state** — tax rate, reinvest %, and member %s are stored in `st.session_state` so edits survive rerenders without persisting to Firestore. "Save as Defaults" is the explicit save action.
- **No module-level DB imports** — all `from sa_rebuild.finance_tracker.db import ...` calls are lazy, matching the pattern in LLC Compliance.

---

## Known Limitations

- **Brand dominance is a heuristic.** Fuzzy name matching between the buy-box seller and the product brand is imperfect — always verify manually when the `brand_dominant` flag is set.
- **Sales estimates are estimates.** Keepa's `monthlySold` reflects Amazon's "X+ bought" badge, not verified sales data.
- **FBA fee tables drift.** Amazon periodically updates fulfillment fees. Update `fba/analytics/fees.py` when Amazon publishes new rates.
- **No own-inventory awareness.** The calculator doesn't factor in stock you already hold at FBA.
- **Keepa token budget is shared.** If you run multiple sessions simultaneously, they compete for the same 60-token bucket.
- **Firestore index required on first deploy.** The run history query needs a single-field index on `fba_runs.started_at`. Firestore will surface a clickable link in the app logs the first time it's needed.
- **Large runs accumulate Firestore documents.** A 1500-row run writes 1500 documents to `fba_output`. Use the Delete or Clear History buttons after downloading your report to keep Firestore lean.
