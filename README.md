# sa-rebuild — FBA Sourcing Calculator

Reads a CSV of UPCs and/or ASINs + wholesale costs and produces a
per-row viability report — recommended sell price, fees, ROI, monthly
sales, dominance, storefront link, and a Buy / Caution / Skip verdict —
using only your Keepa Pro key.

Output mirrors a SellerAmp "FBA" profile (US, FBA, New only).

> **Version history**
> `0.x.x` — desktop app era (macOS .app / Windows .exe, archived on the
> `os_based_build` branch)
> `1.x.x` — web app era (Streamlit Community Cloud, current `main` branch)

---

## For non-developers — use the web app

No installation required. Open the app in your browser, enter your
Keepa API key in the sidebar, upload a CSV, click **Start run**.

**App URL:** *(deploy to Streamlit Community Cloud and paste URL here)*

### Step 1 — Get your Keepa API key

1. Sign in at [keepa.com](https://keepa.com).
2. Go to **API access** → copy the **Private API access key** (a long
   random string starting with a letter or number).

### Step 2 — Prepare your CSV

Download the template from inside the app (the **"Download CSV template"**
button in section 1), then fill it in:

| Column | Required? | Notes |
|---|---|---|
| `upc` | One of these two | 12-digit barcode from your product |
| `asin` | One of these two | Amazon's 10-character identifier |
| `cost` | Yes | Your wholesale cost per unit, in USD |
| `weight_lbs` | No | Overrides Keepa's package weight when filled |
| `prep_cost` | No | Defaults to $0 |

**Excel tip:** format the `upc` column as **Plain text** before pasting,
otherwise long codes turn into scientific notation (`8.83503E+11`).

You can list the same UPC/ASIN multiple times at different costs to
find the break-even price.

### Step 3 — Run the analysis

1. Open the app URL above.
2. Paste your Keepa API key in the **left sidebar** under "Setup". It is
   used only for this session and never stored in the code or repo.
3. Upload your CSV with the drag-and-drop box in section 2.
4. Click **Start run**.
5. Watch live progress. Each row takes roughly 7–8 minutes at steady
   state (Keepa Pro gives you 60 tokens, refilling 1/min; each product
   fetch costs ~6–8 tokens).
6. When the run finishes, click **Download report** to save the CSV.

### Step 4 — If a run is interrupted

If you close the browser tab mid-run, the worker stops. The next time
you open the app the **Resume previous run** button will appear — click
it to pick up from where it left off. The output CSV is appended
row-by-row as the run progresses, so completed rows are never lost.

### Understanding the report

See the [Output](#output) section below for a full column reference and
an explanation of the Buy / Caution / Skip labels.

---

## For developers — run locally or contribute

### Requirements

- Python 3.10 or later
- A Keepa Pro API key

### Setup

```bash
git clone https://github.com/Emanoid/selleramp_rebuild.git
cd selleramp_rebuild
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Optionally create a `.env` file in the repo root to avoid typing your
key every session:

```
KEEPA_API_KEY=your_key_here
```

### Run the web app locally

```bash
streamlit run src/sa_rebuild/web/app.py
```

Streamlit opens the browser automatically. The app is identical to the
hosted version.

### Run the tests

```bash
pytest -q
```

42 offline tests covering fees parity, pricing rule, dominance scoring,
viability labels, variation fetching, CSV I/O, and state durability.
No API key is required — all Keepa responses are mocked.

### Deploy to Streamlit Community Cloud

1. Fork or push the `main` branch to a public GitHub repo.
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with
   GitHub, click **New app**.
3. Select the repo, branch `main`, main file
   `src/sa_rebuild/web/app.py`.
4. Click **Deploy**. No secrets needed — the API key is entered via the
   sidebar UI.

### Project layout

```
src/sa_rebuild/
├── web/
│   └── app.py          # Streamlit UI (entry point for Streamlit Cloud)
├── cli.py              # Typer CLI (run, resume, status, cache)
├── config.py           # AppConfig (Pydantic) — loaded from config.yaml + .env
├── runner.py           # Orchestrates per-row processing, token waits
├── keepa_client.py     # Token-aware Keepa wrapper + 24h SQLite cache
├── token_bucket.py     # Local mirror of Keepa's token bucket
├── cache.py            # SQLite TTL cache
├── state.py            # Atomic per-row checkpoints + resume
├── csv_io.py           # Input parsing + append-on-row report writer
├── keepa_data.py       # CSV/timestamp/seller-history/live-offer helpers
├── report.py           # Assembles the per-UPC output row
└── analytics/
    ├── pricing.py      # Recommended sell price (avg30 + buy box rule)
    ├── competition.py  # Amazon/brand dominance, FBA/FBM seller counts
    ├── sales.py        # monthlySold + leaf-category BSR percentile
    ├── fees.py         # Referral + FBA + inbound + misc%
    ├── variations.py   # Sibling viability + parent monthly sales
    └── viability.py    # Composite Buy / Caution / Skip label
tests/
.streamlit/
└── config.toml         # Upload limit (50 MB), headless mode
config.yaml             # Tunable thresholds (fees, BSR%, ROI, etc.)
requirements.txt        # Python dependencies for Streamlit Cloud
```

### Tuning (`config.yaml`)

| Section | What to change |
|---|---|
| `fees` | Inbound $/lb, misc %, prep cost, per-category referral overrides |
| `pricing` | CV thresholds for volatility-based price hedging |
| `competition` | Amazon/brand dominance cutoffs, fuzzy-match score |
| `viability` | Min profit ($1), min ROI (30%), max BSR% (2%), max FBA sellers |
| `variations` | `fetch_max`, `max_seller_count`, `buy_box_min_ratio` |
| `category_sizes` | Leaf categories used to compute BSR%. Add ones you source from. |

Defaults mirror a SellerAmp FBA profile: inbound $0.80/lb, misc 6.63%,
max BSR 2%, min profit $1.00, min ROI 30%.

### Environment variables

| Variable | What it does |
|---|---|
| `KEEPA_API_KEY` | Pre-fills the API key instead of typing it in the sidebar. |
| `SA_REBUILD_HOME` | Override the data folder (cache, state, output, input). Defaults to `~/.sa-rebuild/`. |

---

## Token reality

Keepa Pro = **60-token bucket, refilling 1/min**. A full product fetch
costs roughly **6–8 tokens**. That means:

- Burst: ~7–10 products back-to-back before the bucket runs dry.
- Steady state: ~1 product every 7–8 minutes.
- 100-row CSV ≈ 11–13 hours wall time.
- Sibling-variation fetches add ~7 tokens per sibling.

The app is built for this reality:

- Per-row state checkpoints (`state/run_<id>.json`)
- Append-on-row CSV output — usable and downloadable mid-run
- 24h on-disk response cache — re-running the same UPC costs 0 tokens
- Auto-pause when wait exceeds `runtime.max_wait_minutes`; resume picks
  up exactly where it left off

---

## Output

Every report starts with a header row and a **column-help row** (the
`upc` cell is tagged `[COLUMN HELP — skip this row]` so you can filter
it in Excel). To skip it in pandas: `pd.read_csv(path, skiprows=[1])`.

### Columns

| Column | What it means |
|---|---|
| `upc`, `asin`, `title`, `brand` | Identifiers and product name |
| `category_root`, `category_leaf` | Top-level + most-specific Amazon category |
| `is_variation`, `variation_count` | True + sibling count when this is a variation child |
| `viable_variations` | Siblings whose buy box ≥ rec price AND sellers < threshold. Populated only when Variations > 0. |
| `cost`, `weight_lbs`, `inbound_cost`, `prep_cost` | Your inputs + derived inbound shipping |
| `current_lowest_fba_new` | Cheapest live FBA-New offer |
| `current_lowest_live_new` | Cheapest live New offer (any fulfillment) |
| `current_buy_box` | Buy-box price right now |
| `buy_box_30d_avg` | Time-weighted mean buy-box price over last 30 days |
| `buy_box_volatility_cv` | stddev/mean over last 90 days. <0.05 = stable |
| `buybox_oos_pct_30d` | % of last 30 days the buy box was empty |
| `recommended_sell_price` | See pricing rule below |
| `referral_fee`, `fba_fulfillment_fee`, `misc_fee`, `total_fees` | Amazon-side fees |
| `estimated_profit`, `roi_pct` | sell − cost − fees − inbound − prep, then ROI |
| `monthly_sales` | Estimated units/month for this ASIN |
| `parent_monthly_sales` | Same for the variation parent (populated when Variations > 0) |
| `bsr`, `bsr_pct` | Current rank + rank as % of leaf category size |
| `live_fba_seller_count`, `live_fbm_seller_count` | Currently-live seller counts |
| `top_buybox_seller_name` / `_share_pct` | Most-frequent buy-box winner in last 30 days |
| `amazon_buybox_share_pct`, `amazon_dominant`, `brand_dominant`, `dominance_label` | Competition diagnostics |
| `storefront_url` | Direct link to the Amazon listing |
| `viability_label` | One-glance verdict |
| `notes` | Free-text caveats |

### Pricing rule

1. Anchor on the 30-day buy-box average.
2. If avg30 < current buy box (market spiked) → use **mean(avg30, current_bb)** to avoid chasing the spike.
3. If avg30 ≥ current buy box (market dipped or unchanged) → use avg30.
4. No buy-box data → fall back to the lowest current live listing.

### Viability labels

| Label | Meaning |
|---|---|
| `Buy` | Profit ≥ $1, ROI ≥ 30%, not dominated, BSR in top 2%, ≤ 15 live FBA sellers |
| `Caution — thin margin` | Profitable but below profit/ROI thresholds |
| `Caution — crowded` | Profitable but too many FBA sellers |
| `Skip — Sell price below cost` | Market price is below your cost |
| `Skip — Amazon dominant` | Amazon held buy box ≥ 70% of last 90 days |
| `Skip — Brand dominant (heuristic)` | Single 3P seller matching the brand name held ≥ 60%. Verify manually. |
| `Skip — Slow seller` | BSR > 2% of leaf category |
| `Pass` | Not profitable |

---

## Variations (optional)

Disabled by default. Enable in the sidebar slider or in `config.yaml`:

```yaml
variations:
  fetch_max: 10          # 0 = disabled; sidebar slider overrides
  max_seller_count: 10   # sibling viable if total live sellers < this
  buy_box_min_ratio: 1.0 # sibling buy box must be ≥ this × rec_price
```

Each sibling fetch costs ~7 tokens. Use when the scanned UPC doesn't
pencil out but you want to check whether a different size or color of
the same product does.

**Why per-child stats matter:** SellerAmp's headline "Est. Sales" is the
parent total across all siblings (e.g. 1,630/mo across 269
size+color combos for Crocs). The per-child number — what your specific
size/color actually moves — is what predicts whether your unit sells.
This tool reports the per-child number by default.

---

## Known limitations

- **Brand dominance is a heuristic.** Fuzzy name matching between brand
  and seller is imperfect. Always check manually when flagged.
- **Sales estimates are estimates.** Keepa's `monthlySold` reflects
  Amazon's "X+ bought" badge, not verified ground truth.
- **FBA fee tables drift.** The local fallback fee table is coarse —
  update `analytics/fees.py` when Amazon publishes new rates.
- **No own-inventory awareness.** Doesn't factor stock you already hold.
