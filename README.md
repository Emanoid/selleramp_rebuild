# CentralLine Sourcing Toolbox

Internal tools for Central Line Group LLC — Amazon FBA sourcing and business compliance.

**Live app:** [centralline-tools.streamlit.app](https://centralline-tools.streamlit.app)

> **Version history**
> `0.x.x` — desktop app era (macOS .app / Windows .exe, archived on `os_based_build`)
> `1.x.x` — web app era (Streamlit Community Cloud, deployed from `main`)

---

## Table of Contents

- [FBA Calculator](#-fba-calculator)
  - [What it does](#what-it-does)
  - [For users](#for-users)
  - [For developers](#for-developers)
- [LLC Compliance Tracker](#-llc-compliance-tracker)
  - [What it does](#what-it-does-1)
  - [For users](#for-users-1)
  - [For developers](#for-developers-1)
- [Known Limitations](#known-limitations)

---

## 🧮 FBA Calculator

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

1. Open the app and select **FBA Calculator** in the sidebar.
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

The FBA Calculator uses Firestore (via the same Firebase project as the LLC tool) to persist run state and output rows across Streamlit server restarts. Locally, if Firebase is configured it uses Firestore; the CLI (`sa-rebuild run`) uses disk state regardless.

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

The FBA Calculator stores all run state and output rows in Firestore (`fba_runs` and `fba_output` collections), so data survives Streamlit server restarts. The Run History panel and Clear History button in the UI manage these collections directly.

#### Code layout — FBA Calculator

```
src/sa_rebuild/
├── config.py                   # AppConfig (Pydantic settings) — shared by both tools
├── paths.py                    # Runtime data dirs (cache, state, output) — shared
├── web/
│   ├── app.py                  # Entry point — navigation wirer
│   ├── home.py                 # Landing page (two-column tool cards)
│   └── pages/
│       └── 1_FBA_Calculator.py # FBA sourcing tool UI
└── fba/                        # All FBA Calculator source code
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

**FBA Calculator:**

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

## FBA Calculator — Full Behavior Reference

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

## Known Limitations

- **Brand dominance is a heuristic.** Fuzzy name matching between the buy-box seller and the product brand is imperfect — always verify manually when the `brand_dominant` flag is set.
- **Sales estimates are estimates.** Keepa's `monthlySold` reflects Amazon's "X+ bought" badge, not verified sales data.
- **FBA fee tables drift.** Amazon periodically updates fulfillment fees. Update `fba/analytics/fees.py` when Amazon publishes new rates.
- **No own-inventory awareness.** The calculator doesn't factor in stock you already hold at FBA.
- **Keepa token budget is shared.** If you run multiple sessions simultaneously, they compete for the same 60-token bucket.
- **Firestore index required on first deploy.** The run history query needs a single-field index on `fba_runs.started_at`. Firestore will surface a clickable link in the app logs the first time it's needed.
- **Large runs accumulate Firestore documents.** A 1500-row run writes 1500 documents to `fba_output`. Use the Delete or Clear History buttons after downloading your report to keep Firestore lean.
