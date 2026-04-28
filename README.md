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

A live replacement for the Excel compliance tracker. Tracks all quarterly,
annual, and one-time filing requirements for Central Line Group LLC. Check
off filings, log confirmation numbers, see what's due next, and review the
full audit history of who changed what and when. Login required (Firebase).

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

1. Open the app and select **LLC Compliance** in the sidebar.
2. Sign in with your email and password (set up by the admin).
3. Use the **Dashboard** tab for an overview of what's done, overdue, and coming up.
4. Use the **Quarterly / Annual / One-Time** tabs to check off filings:
   - Edit the **Status** column (`Pending` → `Done` or `Overdue`)
   - Fill in **Date Filed** and **Conf. #** when marking done
   - Click **Save changes**
5. Use **Add a filing row** to add new requirements.
6. Use **View change history** to see who changed what and when.

---

## For developers — run locally

### Requirements

- Python 3.10 or later
- A Keepa Pro API key (for FBA Calculator)
- Firebase project credentials (for LLC Compliance — see `compliance_tool_plan.md`)

### Setup

```bash
git clone https://github.com/Emanoid/selleramp_rebuild.git
cd selleramp_rebuild
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Copy `.env` and fill in your keys:

```
KEEPA_API_KEY=your_keepa_key_here

FIREBASE_PROJECT_ID=your-project-id-here
FIREBASE_WEB_API_KEY=your-web-api-key-here
FIREBASE_SERVICE_ACCOUNT=service_account.json
```

Drop `service_account.json` (downloaded from Firebase) into the repo root.

### Run locally

```bash
streamlit run src/sa_rebuild/web/app.py
```

### Run the tests

```bash
pytest -q
```

42 offline tests — no API key required, all Keepa responses are mocked.

### Seed the compliance database

Run once after setting up Firebase (see `compliance_tool_plan.md`):

```bash
python scripts/seed_compliance.py path/to/CentralLineGroup_Compliance_Tracker.xlsx
```

Re-runnable safely — existing rows are updated in place, new rows are added.
Preview without writing: add `--dry-run`.

### Deploy to Streamlit Community Cloud

1. Push `main` to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**.
3. Repo: `Emanoid/selleramp_rebuild`, branch: `main`, file: `src/sa_rebuild/web/app.py`.
4. Under **Settings → Secrets**, add all `.env` values plus `FIREBASE_SERVICE_ACCOUNT_JSON`
   (paste the full contents of `service_account.json`).
5. Click **Deploy**.

### Project layout

```
src/sa_rebuild/
├── web/
│   ├── app.py                  # Entry point — navigation wirer
│   ├── home.py                 # Landing page
│   └── pages/
│       ├── 1_FBA_Calculator.py # FBA sourcing tool
│       └── 2_LLC_Compliance.py # Compliance tracker (Firebase-backed)
├── compliance/
│   ├── firebase_client.py      # Cached Firestore client
│   ├── auth.py                 # Firebase Auth REST API sign-in
│   └── db.py                   # Firestore CRUD + audit history
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
└── seed_compliance.py          # Excel → Firestore import
tests/
config.yaml                     # Tunable FBA thresholds
compliance_tool_plan.md         # Firebase setup guide
deployment.md                   # Streamlit Cloud + Namecheap DNS guide
```

### Environment variables

| Variable | Tool | What it does |
|---|---|---|
| `KEEPA_API_KEY` | FBA Calculator | Pre-fills the API key in the sidebar |
| `SA_REBUILD_HOME` | FBA Calculator | Override data folder (cache, state, output). Default: `~/.sa-rebuild/` |
| `FIREBASE_PROJECT_ID` | LLC Compliance | Firebase project identifier |
| `FIREBASE_WEB_API_KEY` | LLC Compliance | Firebase Web API key (for user sign-in) |
| `FIREBASE_SERVICE_ACCOUNT` | LLC Compliance | Path to service account JSON (local) |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | LLC Compliance | Full JSON content (Streamlit Cloud secrets) |

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
