# sa-rebuild — SellerAmp-style FBA Sourcing Calculator (Keepa-only)

A desktop app (also a Python CLI) that reads a CSV of UPCs and/or ASINs + wholesale
costs and produces a per-row viability report — recommended sell price, fees,
ROI, monthly sales, dominance, storefront link, Buy/Caution/Skip label,
optional sibling-variation analysis — using only your Keepa Pro key.

Output mirrors your SellerAmp "FBA" profile (US, FBA, New only).

---

## For non-developers — Download and run the desktop app

You don't need to install Python or know any code. You download one file,
double-click it, use it from your browser. **Full step-by-step screenshots
and troubleshooting are in [`USER_GUIDE.md`](USER_GUIDE.md).** Quick version:

### 1. Get your Keepa API key

Sign in at https://keepa.com → "API access" → copy the **Private API access
key** (a long random string). You'll paste it into the app on first launch.

### 2. Download the binary

Go to the **[Releases page](../../releases)** of this repo and grab the
latest:

- **Mac users** → download `sa-rebuild-mac.zip`
- **Windows users** → download `sa-rebuild-windows.zip`

> If you don't see any releases, the maintainer hasn't tagged one yet. See
> the [Releasing](#releasing-trigger-the-build) section below — it takes
> ~10 minutes from a single tag push.

### 3. Run it

**macOS**

1. Double-click `sa-rebuild-mac.zip` to unzip → you'll get `sa-rebuild.app`.
2. Drag it into your **Applications** folder.
3. The first time you open it, macOS will warn it's from an unidentified
   developer. **Right-click** the app → **Open** → click **Open** in the
   dialog. (One-time only — after that, normal double-click works.)

**Windows**

1. Right-click `sa-rebuild-windows.zip` → **Extract All…**.
2. Open the extracted folder, double-click `sa-rebuild.exe`.
3. Windows SmartScreen may say "Windows protected your PC." Click
   **More info** → **Run anyway**. (One-time only.)

### 4. Use the app

- A small terminal window opens (don't close it — that's the engine).
- Your browser auto-opens to `http://127.0.0.1:<port>` after a few seconds.
- In the **left sidebar**, paste your Keepa key. It saves automatically.
- Click **Download CSV template**, fill in your products, save as CSV.
- **Drag the CSV** onto the upload box.
- Click **Start run**. Watch live progress. Download the report when done.

When you're finished, close the terminal window to shut the app down.

### 5. Where your data lives (all local, never uploaded)

- **Mac:** `~/.sa-rebuild/`
- **Windows:** `C:\Users\<you>\.sa-rebuild\`

Inside: `settings.json` (your key), `cache/`, `state/`, `output/`, `input/`.
Safe to delete `cache/` to reclaim disk; **don't** delete `settings.json`
unless you want to re-enter your key.

For the long form (Gatekeeper bypass, troubleshooting, label meanings,
running on a schedule), read [`USER_GUIDE.md`](USER_GUIDE.md).

---

<a name="releasing-trigger-the-build"></a>
## Releasing — trigger the build that produces the binaries

The Mac and Windows binaries are built **automatically by GitHub Actions** —
you don't need a Mac or Windows machine yourself to ship them. Two paths:

### Path A — Tag a release (the normal way)

```bash
# from the repo root, on the master branch:
git tag v0.1.0
git push origin v0.1.0
```

GitHub Actions then:

1. Spins up a macOS runner and a Windows runner (free for public repos).
2. Runs the unit tests on both (fails fast if anything broke).
3. Builds the bundle with PyInstaller on each.
4. Zips the result and **attaches `sa-rebuild-mac.zip` and
   `sa-rebuild-windows.zip` to the v0.1.0 Release page** under
   "Releases" on your repo home.

End users grab them from `https://github.com/<you>/<repo>/releases/latest`.

Total time: ~10–15 minutes from tag push to binaries downloadable.

### Path B — Manual build without tagging (dry run)

If you want to confirm the build works before tagging:

1. Go to your repo's **Actions** tab on GitHub.
2. Click **Build and release desktop binaries** in the left list.
3. Click **Run workflow** → choose `master` → click the green button.
4. After it finishes (~10 min), click into the run and download
   `sa-rebuild-mac.zip` / `sa-rebuild-windows.zip` from the **Artifacts**
   section at the bottom. (Workflow-dispatch artifacts aren't published as
   a Release — they're only available to repo collaborators.)

> If you don't see the workflow in the Actions tab, the workflow file
> (`.github/workflows/release.yml`) isn't on your **default branch** yet.
> Merge it from `working` to `master` (or whichever branch is default).

### Building locally for development (advanced)

You don't need this unless you're debugging the bundling itself.

```bash
# Mac:
packaging/build-mac.sh
# → produces dist/sa-rebuild.app

# Windows (run from cmd.exe in repo root):
packaging\build-windows.bat
# → produces dist\sa-rebuild\sa-rebuild.exe

# Cross-platform: just run the Streamlit UI from source, no bundling:
streamlit run src/sa_rebuild/web/app.py
```

---

## For developers — CLI / library use

Everything below is for developers who want to run the analysis from the
command line or extend the codebase.

## Token reality

Keepa Pro = **60-token bucket, refill 1/min**. A full product fetch ≈ **6–8
tokens**. So you can burst ~7–10 products instantly, then steady-state ~1
product every 7–8 minutes.

A 100-row CSV ≈ 11–13 hours wall time. Sibling-variation fetches add ~7
tokens each. The tool is built for this:

- Every-row state checkpoint (`state/run_<id>.json` + `state/last_run.json`)
- Append-on-row CSV output (usable mid-run)
- 24h on-disk response cache (`cache/keepa.sqlite`)
- Graceful pause when wait > `runtime.max_wait_minutes` — exit 0 with a clear
  resume message
- `sa-rebuild resume` (no args) picks up where the last run left off

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env     # add your KEEPA_API_KEY
```

## Input CSV

Required: `cost`, plus **at least one** of `upc` or `asin`. Optional:
`weight_lbs` (overrides Keepa's package weight), `prep_cost`.

```csv
upc,asin,cost,weight_lbs,prep_cost
028800127321,,8.91,0.73,0.00
,B005ET6J2K,8.91,0.73,0.00
883503388642,,31.43,0.40,0.00
```

**Rules:**
- `asin` wins when both columns are filled on the same row (skips UPC→ASIN
  resolution).
- Blank `weight_lbs` → Keepa's package weight is used (less accurate).
- Blank `prep_cost` → treated as $0.
- The same UPC/ASIN on multiple rows is fine — each row evaluates
  independently against its own `cost`. Useful for "at what cost would this
  pencil out?" analysis.

**Excel gotcha:** format the `upc` column as **Plain text** before pasting,
otherwise long codes become scientific notation (`8.83503E+11`). ASINs are
text-safe.

## Run

```bash
sa-rebuild run --input input/products.csv
# custom output path:
sa-rebuild run -i input/products.csv -o output/today.csv
# also score up to 10 sibling variations per variation parent (costs ~7
# tokens per sibling fetched + 7 for the parent monthly_sales lookup):
sa-rebuild run -i input/products.csv --variations 10
# strip the column-help row (cleaner for pandas/Excel imports):
sa-rebuild run -i input/products.csv --no-descriptions
```

Output goes to `output/report_<timestamp>.csv` by default.

If your token bucket runs out mid-run, you'll see:

```
Pausing run. 47 rows remain. Resume with: sa-rebuild resume
```

After tokens regenerate, just run:

```bash
sa-rebuild resume
```

It re-reads `state/last_run.json`, skips already-done rows, and continues
appending to the same output CSV.

## Other commands

```bash
sa-rebuild status                                # last-run progress
sa-rebuild cache clear --older-than-hours 24
sa-rebuild resume --run-id 20260425T120000-abc123
```

## Output

Every report begins with the header row, then a **column-help row** in plain
English (the `upc` cell of that row is tagged `[COLUMN HELP — skip this row]`
so you can filter it out). Disable with `--no-descriptions`. To skip it in
pandas: `pd.read_csv(path, skiprows=[1])`.

### Columns

| Column | What it means |
|---|---|
| `upc`, `asin`, `title`, `brand` | Identifiers + name |
| `category_root`, `category_leaf` | Top-level + most-specific Amazon category. Leaf is used for BSR%. |
| `is_variation`, `variation_count` | True + sibling count when this is a child of a variation parent. |
| `viable_variations` | Sibling ASINs whose **current buy box ≥ recommended_sell_price** AND **total live sellers < `variations.max_seller_count`**. Format: `ASIN (Size:8, Color:White) bb=$45.00 sellers=4 \| ASIN2 (...)`. Empty unless `--variations N` set. |
| `cost`, `weight_lbs`, `inbound_cost`, `prep_cost` | Your inputs + derived inbound shipping. |
| `current_lowest_fba_new` | Cheapest live FBA-New offer. Blank if none. |
| `current_lowest_live_new` | Cheapest live New offer of any fulfillment. |
| `current_buy_box` | Buy-box price right now (with shipping). Blank when buy box is empty. |
| `buy_box_30d_avg` | Time-weighted mean buy-box price over last 30 days. |
| `buy_box_volatility_cv` | stddev/mean of buy-box price over last 90 days. <0.05 = stable. |
| `buybox_oos_pct_30d` | % of last 30 days buy box was empty (no eligible seller). |
| `recommended_sell_price` | See **Pricing rule** below. |
| `referral_fee`, `fba_fulfillment_fee`, `misc_fee`, `total_fees` | Amazon-side fees. |
| `estimated_profit`, `roi_pct` | sell − cost − total_fees − inbound − prep, then ROI. |
| `monthly_sales` | Estimated units sold per month for THIS ASIN (the variation child). Source priority: Keepa `monthlySold` → `monthlySoldHistory` latest → `salesRankDrops30`. |
| `parent_monthly_sales` | Same metric for the variation **parent** (sums siblings). Only populated when `--variations N>0`. |
| `bsr`, `bsr_pct` | Current rank in leaf category, plus that as % of category size. |
| `live_fba_seller_count`, `live_fbm_seller_count` | Distinct currently-live sellers. |
| `top_buybox_seller_name` / `_share_pct` | Most-frequent buy-box winner in last 30d. |
| `amazon_buybox_share_pct`, `amazon_dominant`, `brand_dominant`, `dominance_label` | Competition diagnostics. |
| `storefront_url` | Click-through to the listing. |
| `viability_label` | One-glance verdict — see below. |
| `notes` | Free-text caveats. |

### Pricing rule (`recommended_sell_price`)

1. Anchor on the 30-day buy-box average.
2. If avg30 < current buy box (market moved up recently) → use **mean(avg30,
   current_bb)** so we don't chase the spike.
3. Otherwise (avg30 ≥ current_bb, market dipped or unchanged) → use avg30.
4. If no buy-box data at all → fall back to lowest current live listing.

### Viability labels

- `Buy` — profit ≥ $1.00, ROI ≥ 30%, not dominated, BSR in top 2%, ≤15 live FBA sellers
- `Caution — thin margin` — profitable but below thresholds
- `Caution — crowded` — profitable but too many FBA sellers
- `Skip — Sell price below cost` — market is below your cost; do not buy
- `Skip — Amazon dominant` — Amazon held buy box ≥ 70% of last 90 days
- `Skip — Brand dominant (heuristic)` — single 3P seller named like the brand held buy box ≥ 60% of last 90 days. Always verify manually.
- `Skip — Slow seller` — BSR > 2% of leaf category
- `Pass` — not profitable

## Variations

Disabled by default. Each sibling fetch costs ~7 Keepa tokens, plus 7 for the
parent if you want `parent_monthly_sales`. Turn on per-run:

```bash
sa-rebuild run -i input/products.csv --variations 10
```

Or persistently in `config.yaml`:

```yaml
variations:
  fetch_max: 10                # 0 disables; CLI flag overrides
  max_seller_count: 10         # sibling viable if total live sellers < this
  buy_box_min_ratio: 1.0       # sibling buy box must be >= this × main rec_price
```

The `viable_variations` column lists only siblings that pass both checks, so
when your scanned UPC doesn't pencil out you can ask the supplier whether
they have one of the listed sibling sizes/colors instead.

**Why per-child stats matter**: SellerAmp's headline "Est. Sales" is the
parent total summed across all siblings (for Crocs that's 1630/mo across 269
size+color combos). The per-child number — what your specific size+color
actually moves — is what predicts whether your unit sells. The tool reports
the per-child number by default and the parent number only when
`--variations N>0`.

## Tuning (`config.yaml`)

- **Fees** — inbound $/lb, misc%, prep, referral overrides per category. Config
  overrides win over Keepa's value, so e.g. `Clothing, Shoes & Jewelry: 0.17`
  forces 17% (Amazon's apparel rate >$15) even when Keepa returns 15%.
- **Pricing** — `cv_stable` / `cv_moderate` thresholds for the volatility-based
  recommended-price hedging.
- **Competition** — Amazon/brand dominance %s, fuzzy-match score for brand
  detection.
- **Viability** — min profit, min ROI, max BSR%, max FBA seller count.
- **Variations** — `fetch_max`, `max_seller_count`, `buy_box_min_ratio`.
- **Category sizes** — used to compute BSR%. Add the leaf categories you
  source from often. Missing categories yield `bsr_pct=None` (the row is
  reported but the slow-seller filter doesn't fire — better than mis-classifying).

The defaults mirror the SellerAmp profile screenshot you provided
(inbound $0.80/lb, misc 6.63%, max BSR 2%, min profit $1.00, min ROI 30%).

## Tests

```bash
pytest -q
```

42 offline tests covering:

- Fees parity (incl. SellerAmp apparel referral override)
- Pricing rule (avg30 vs current buy box, all fallback branches)
- Live-offer filtering via Keepa's `liveOffersOrder` (excludes the historical
  offers Keepa also returns in the same payload)
- Dominance scoring (Amazon, brand-fuzzy-match, open-market)
- Viability labels (incl. below-cost short-circuit)
- Variation viability (sibling fetch cap, threshold filtering, parent
  monthly-sales fetch)
- CSV input (UPC-only, ASIN-only, ASIN-wins-when-both, distinct row IDs for
  duplicate UPCs)
- Description-row writer (with and without)
- State durability (atomic write, resume roundtrip, duplicate-UPC tracking)

## Known limitations

- **Brand-dominance is a heuristic.** Brand name vs seller display name fuzzy
  match is imperfect — the brand often sells through a 3P account that
  doesn't match the brand name. Always tagged "(heuristic)" alongside the
  share %, so you can override.
- **Sales estimates are estimates.** Keepa's `monthlySold` is a reflection of
  Amazon's "X+ bought" badge, not ground truth.
- **FBA fee tables drift.** `analytics/fees.py` prefers Keepa's
  `fbaFees.pickAndPackFee` when present; the local fallback table is coarse
  — update when Amazon publishes new rates.
- **Per-child stats by design.** The tool reports per-ASIN (variation child)
  metrics, not parent-aggregate. This is more accurate for sourcing
  decisions, but differs from SellerAmp's default headline numbers. Use
  `--variations N` to also fetch the parent and siblings.
- **No own-inventory awareness.** Doesn't factor stock you already hold.

## Layout

```
src/sa_rebuild/
├── cli.py              # typer entrypoint (run, resume, status, cache)
├── config.py           # AppConfig (pydantic) loaded from config.yaml + .env
├── keepa_client.py     # token-aware Keepa wrapper + cache
├── token_bucket.py     # local mirror of Keepa's bucket
├── cache.py            # sqlite TTL cache
├── state.py            # atomic per-row checkpoints, resume
├── csv_io.py           # input parsing + append-on-row report writer
│                       #   (incl. COLUMN_DESCRIPTIONS for the help row)
├── keepa_data.py       # CSV/timestamp/seller-history/live-offer helpers
├── report.py           # assemble per-UPC output row
└── analytics/
    ├── pricing.py      # recommended sell price (avg30 + current buy box rule)
    ├── competition.py  # Amazon/brand dominance, FBA/FBM seller counts
    ├── sales.py        # monthlySold + leaf-category BSR percentile
    ├── fees.py         # referral + FBA fulfill + inbound + misc%
    ├── variations.py   # opt-in sibling viability + parent monthly sales
    └── viability.py    # composite Buy/Caution/Skip label
```
