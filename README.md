# CentralLine Sourcing Toolbox

Internal tools for Central Line Group LLC — Amazon FBA sourcing and business compliance.

**App URL:** [tools.centrallinegroup.com](https://tools.centrallinegroup.com) — also directly at [centralline-tools.streamlit.app](https://centralline-tools.streamlit.app)

> **Version history**
> `0.x.x` — desktop app era (macOS .app / Windows .exe, archived on `os_based_build`)
> `1.x.x` — web app era (Streamlit Community Cloud, current `main` branch)

---

## Tools

### 🧮 FBA Calculator

Upload a CSV of UPCs or ASINs with your wholesale cost. Get a per-row
Buy / Caution / Skip verdict — recommended sell price, fees, ROI, monthly
sales, competition analysis, and a direct Amazon storefront link.
Powered by your Keepa Pro key. No login required.

### 📋 LLC Compliance Tracker

Live replacement for the Excel compliance tracker. Tracks all quarterly,
annual, and one-time filing requirements for Central Line Group LLC.

| Tab | What it does |
|---|---|
| Dashboard | Overdue + upcoming filings at a glance; filing quick-reference table |
| Quarterly | NJ Sales Tax, Federal/NJ estimated tax — filter by year, quarter, assignee |
| Annual | Form 1065, NJ-1065, personal 1040s — filter by year, assignee |
| One-Time | Setup items (bank account, Amazon seller account, BOI report, etc.) |
| Settings | Edit company name/formation date; manage members; sync assignees from filings |

Key features: login required (Firebase Auth), full audit trail of every status
change, CSV import/export, row reordering, confirmation number tracking.

---

## For non-developers — FBA Calculator

### Step 1 — Get your Keepa API key

1. Sign in at [keepa.com](https://keepa.com).
2. Go to **API access** → copy the **Private API access key**.

### Step 2 — Prepare your CSV

Download the template from inside the app (**"Download CSV template"** button),
then fill it in:

| Column | Required? | Notes |
|---|---|---|
| `upc` | One of these two | 12-digit barcode |
| `asin` | One of these two | Amazon's 10-character identifier |
| `cost` | Yes | Wholesale cost per unit, in USD |
| `weight_lbs` | No | Overrides Keepa's package weight |
| `prep_cost` | No | Defaults to $0 |

**Excel tip:** format the `upc` column as **Plain text** before pasting —
long codes turn into scientific notation (`8.83503E+11`) otherwise.

### Step 3 — Run the analysis

1. Open the app and select **FBA Calculator** in the sidebar.
2. Paste your Keepa API key under "Setup" in the left sidebar.
3. Upload your CSV and click **Start run**.
4. Watch live progress — each row takes ~7–8 minutes at steady state.
5. Click **Download report** when the run finishes.

### Step 4 — If a run is interrupted

Close the browser mid-run and the worker stops. Re-open the app and click
**Resume previous run** — it picks up exactly where it left off. Completed
rows are never lost.

---

## For non-developers — LLC Compliance Tracker

### Sign in

1. Open the app → select **LLC Compliance** in the sidebar.
2. Sign in with your email and password (accounts created by the admin in Firebase Console → Authentication).

### Day-to-day use

- **Dashboard** — see overdue filings in red and the next 5 upcoming deadlines at a glance.
- **Quarterly / Annual / One-Time tabs** — select a row and click **Edit** to update status, date filed, confirmation number, or notes. Every status change is logged automatically.
- **Filters** — narrow by status, year, quarter, or assignee. The default view hides Done rows; clear the Status filter to see everything.
- **Add** — click **+ Add** to create a new filing row manually.
- **History** — select a row and click **History** to see every status change with timestamp and who made it.
- **Import** — download the CSV template for the tab, fill it in, and upload via **Import from CSV**.
- **Reorder** — select a row and use **↑ Up / ↓ Down** to change display order within a tab.

### Managing members and company info (Settings tab)

- **Company Info** — edit the company name or formation date shown in the page header.
- **Members** — the names that appear in every "Assigned To" dropdown. Add members manually, or click **Sync now** to automatically pull all unique assignee names from existing filings.
- **Removing a member** — clicking Remove opens a dialog showing how many filings reference that person. You must reassign those filings (to an existing member or a new name) before the removal is confirmed. Filings are updated in the database immediately.

---

## For developers — general setup

```bash
git clone https://github.com/Emanoid/selleramp_rebuild.git
cd selleramp_rebuild
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Run the app

```bash
streamlit run src/sa_rebuild/web/app.py
```

### Run the tests

```bash
pytest -q
```

42 offline tests — no API key required, all Keepa responses are mocked.

---

## For developers — FBA Calculator

### Environment

Add to `.env`:

```
KEEPA_API_KEY=your_keepa_key_here
```

`SA_REBUILD_HOME` optionally overrides the data folder (cache, state, output). Default: `~/.sa-rebuild/`.

### Deploy to Streamlit Community Cloud

1. Push `main` to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**.
3. Repo: `Emanoid/selleramp_rebuild`, branch: `main`, file: `src/sa_rebuild/web/app.py`.
4. Under **Settings → Secrets**, add `KEEPA_API_KEY`.
5. Click **Deploy**.

---

## For developers — LLC Compliance Tracker

### Environment

Add to `.env`:

```
FIREBASE_PROJECT_ID=your-project-id-here
FIREBASE_WEB_API_KEY=your-web-api-key-here
FIREBASE_SERVICE_ACCOUNT=service_account.json
```

Drop `service_account.json` (downloaded from Firebase Console → Service Accounts) into the repo root. See `compliance_tool_plan.md` for the full Firebase project setup guide.

### Deploy to Streamlit Community Cloud

1. Push `main` to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**.
3. Repo: `Emanoid/selleramp_rebuild`, branch: `main`, file: `src/sa_rebuild/web/app.py`.
4. Under **Settings → Secrets**, add `FIREBASE_PROJECT_ID`, `FIREBASE_WEB_API_KEY`, and `FIREBASE_SERVICE_ACCOUNT_JSON` (paste the full contents of `service_account.json`).
5. Click **Deploy**.

### Project layout

```
src/sa_rebuild/
├── web/
│   ├── app.py                  # Entry point — navigation wirer
│   ├── home.py                 # Landing page (two-column tool cards)
│   └── pages/
│       ├── 1_FBA_Calculator.py # FBA sourcing tool
│       └── 2_LLC_Compliance.py # Compliance tracker (Firebase-backed)
├── compliance/
│   ├── firebase_client.py      # Cached Firestore client
│   ├── auth.py                 # Firebase Auth REST API sign-in
│   └── db.py                   # Firestore CRUD — filings, members, company config
│                               #   get/add/update/delete filings + audit history
│                               #   get/add/delete members, count & reassign by assignee
│                               #   get/save company info, sync members from filings
├── config.py                   # AppConfig (Pydantic)
├── runner.py                   # Per-row Keepa processing + token waits
├── keepa_client.py             # Token-aware Keepa wrapper + 24h cache
├── state.py                    # Atomic checkpoints + resume
├── csv_io.py                   # Input parsing + append-on-row output
├── keepa_data.py               # Keepa response helpers
├── report.py                   # Assembles per-UPC output row
└── analytics/
    ├── pricing.py              # Recommended sell price
    ├── competition.py          # Dominance scoring
    ├── sales.py                # Monthly sales + BSR percentile
    ├── fees.py                 # Referral + FBA + inbound fees
    ├── variations.py           # Sibling viability
    └── viability.py            # Buy / Caution / Skip label
scripts/
└── seed_compliance.py          # Excel → Firestore (filings + members)
tests/
config.yaml                     # Tunable FBA thresholds
compliance_tool_plan.md         # Firebase setup guide
deployment.md                   # Streamlit Cloud + Namecheap DNS guide
```

**Never commit:** `service_account.json`, `streamlit_secrets.toml`, `.streamlit/secrets.toml` — all in `.gitignore`.

### Environment variables

**FBA Calculator**

| Variable | What it does |
|---|---|
| `KEEPA_API_KEY` | Pre-fills the API key in the sidebar |
| `SA_REBUILD_HOME` | Override data folder (cache, state, output). Default: `~/.sa-rebuild/` |

**LLC Compliance Tracker**

| Variable | What it does |
|---|---|
| `FIREBASE_PROJECT_ID` | Firebase project identifier |
| `FIREBASE_WEB_API_KEY` | Firebase Web API key (for user sign-in) |
| `FIREBASE_SERVICE_ACCOUNT` | Path to service account JSON — local dev only |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Full JSON content — Streamlit Cloud secrets |

---

## FBA Calculator — token reality

Keepa Pro = **60-token bucket, refilling 1/min**. A full product fetch
costs roughly **6–8 tokens**:

- Burst: ~7–10 products back-to-back before the bucket runs dry
- Steady state: ~1 product every 7–8 minutes
- 100-row CSV ≈ 11–13 hours wall time
- Sibling-variation fetches add ~7 tokens per sibling

Built for this reality: per-row checkpoints, append-on-row CSV output,
24h on-disk cache (re-running the same UPC costs 0 tokens), auto-pause
and resume.

---

## FBA Calculator — output columns

| Column | What it means |
|---|---|
| `upc`, `asin`, `title`, `brand` | Identifiers and product name |
| `category_root`, `category_leaf` | Top-level + most-specific Amazon category |
| `is_variation`, `variation_count` | True + sibling count when this is a variation child |
| `viable_variations` | Siblings with buy box ≥ rec price and sellers < threshold |
| `cost`, `weight_lbs`, `inbound_cost`, `prep_cost` | Your inputs + derived inbound shipping |
| `current_lowest_fba_new` | Cheapest live FBA-New offer |
| `current_buy_box` | Buy-box price right now |
| `buy_box_30d_avg` | Time-weighted mean buy-box price over last 30 days |
| `buy_box_volatility_cv` | stddev/mean over last 90 days — <0.05 = stable |
| `recommended_sell_price` | See pricing rule below |
| `referral_fee`, `fba_fulfillment_fee`, `misc_fee`, `total_fees` | Amazon-side fees |
| `estimated_profit`, `roi_pct` | sell − cost − fees − inbound − prep, then ROI |
| `monthly_sales` | Estimated units/month for this ASIN |
| `bsr`, `bsr_pct` | Current rank + rank as % of leaf category size |
| `live_fba_seller_count`, `live_fbm_seller_count` | Currently-live seller counts |
| `amazon_buybox_share_pct`, `amazon_dominant`, `brand_dominant` | Competition diagnostics |
| `storefront_url` | Direct link to the Amazon listing |
| `viability_label` | One-glance verdict |
| `notes` | Free-text caveats |

### Pricing rule

1. Anchor on the 30-day buy-box average.
2. If avg30 < current buy box (market spiked) → use **mean(avg30, current_bb)**.
3. If avg30 ≥ current buy box (market dipped or stable) → use avg30.
4. No buy-box data → fall back to the lowest current live listing.

### Viability labels

| Label | Meaning |
|---|---|
| `Buy` | Profit ≥ $1, ROI ≥ 30%, not dominated, BSR top 2%, ≤ 15 FBA sellers |
| `Caution — thin margin` | Profitable but below profit/ROI thresholds |
| `Caution — crowded` | Profitable but too many FBA sellers |
| `Skip — Sell price below cost` | Market price is below your cost |
| `Skip — Amazon dominant` | Amazon held buy box ≥ 70% of last 90 days |
| `Skip — Brand dominant (heuristic)` | Single 3P seller matching the brand held ≥ 60% |
| `Skip — Slow seller` | BSR > 2% of leaf category |
| `Pass` | Not profitable |

---

## Known limitations

- **Brand dominance is a heuristic.** Fuzzy name matching is imperfect — always verify manually when flagged.
- **Sales estimates are estimates.** Keepa's `monthlySold` reflects Amazon's "X+ bought" badge, not ground truth.
- **FBA fee tables drift.** Update `analytics/fees.py` when Amazon publishes new rates.
- **No own-inventory awareness.** Doesn't factor stock you already hold.
