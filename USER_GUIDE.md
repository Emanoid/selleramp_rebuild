# sa-rebuild — User Guide (no Python needed)

This guide is for non-technical users. You'll download a single file, double
click it, and use it from your web browser.

---

## 1. What this tool does

You give it a CSV with UPCs (or ASINs) and your wholesale cost. It looks each
product up on Keepa and tells you, per product:

- Whether it's worth buying (Buy / Caution / Skip)
- The price you should sell at
- Estimated profit, ROI %, monthly sales
- Who's currently winning the buy box
- Whether Amazon or the brand dominates (= you can't compete)
- A clickable link to the Amazon listing

It uses **your own Keepa API key** — no shared accounts, no hosted server.
Everything runs on your computer. Nothing leaves your machine except the
calls you make to Keepa.

---

## 2. What you need before starting

1. **A Keepa Pro account.** Sign in at https://keepa.com → click "API access"
   → copy the **Private API access key** (it's a long random string).
2. **Tokens.** A free Keepa API plan has very few; we recommend Pro
   (60-token bucket, refills 1 token/min). One product look-up costs ~6–8
   tokens. So 7–10 products in a burst, then about 1 product every 7
   minutes. A list of 100 products takes roughly half a day to fully analyze.
3. **5 minutes** for first-time setup.

---

## 3. Download and install

### macOS

1. Go to the **Releases** page on the GitHub repo.
2. Download **`sa-rebuild-mac.zip`**.
3. Double-click it to unzip. You'll get **`sa-rebuild.app`**.
4. Drag `sa-rebuild.app` into your **Applications** folder.

> **macOS Gatekeeper warning** — because this app isn't signed by an Apple
> developer account, the first launch will say *"sa-rebuild can't be opened
> because Apple cannot check it for malicious software."* This is normal
> for free desktop tools. To open it:
>
> 1. Right-click `sa-rebuild.app` (don't double-click).
> 2. Choose **Open** from the menu.
> 3. In the dialog, click **Open** again.
>
> You only need to do this **once**. After that, double-clicking works
> normally.

### Windows

1. Go to the **Releases** page on the GitHub repo.
2. Download **`sa-rebuild-windows.zip`**.
3. Right-click → **Extract All…** → pick a folder (e.g. `Documents\sa-rebuild`).
4. Inside, double-click **`sa-rebuild.exe`**.

> **SmartScreen warning** — Windows will say *"Windows protected your PC."*
> This is normal for unsigned apps. To allow it:
>
> 1. Click **More info**.
> 2. Click **Run anyway**.
>
> One-time only.

---

## 4. First launch

When you double-click the app:

1. A **terminal window** opens showing startup logs. Don't close it — that
   window IS the app. Closing it shuts the tool down.
2. After ~5 seconds your default **web browser** opens automatically to
   `http://127.0.0.1:<some port>`. That's the tool's UI.
3. In the **left sidebar**, paste your Keepa API key into the
   "Keepa API key" field. It saves automatically. You only enter it once
   per machine; it's stored locally in
   `~/.sa-rebuild/settings.json` (Mac) or
   `C:\Users\<you>\.sa-rebuild\settings.json` (Windows).

---

## 5. Running an analysis

1. **Click "Download CSV template"** under "1. Get the input template" and
   open the file in Excel or Google Sheets.
2. Fill in your products. Required columns: `cost`, plus at least one of
   `upc` or `asin`. Optional: `weight_lbs`, `prep_cost`. Save as CSV.

   > **Excel tip**: format the `upc` column as **Plain text** before pasting
   > UPCs, or Excel will mangle long codes into scientific notation
   > (`8.83503E+11`). ASINs are safe.

3. **Drag your CSV** onto the upload area under "2. Upload your CSV".
4. (Optional) In the sidebar, set **"Sibling variations to score per parent"**
   to `10` if you want the tool to also check sibling sizes/colors of any
   variation parent. **Costs ~7 extra Keepa tokens per sibling fetched.**
   Leave at 0 to skip.
5. Click **"Start run"**.

The progress section shows:

- **Rows done / total**
- **Tokens left** (mirrors your Keepa bucket)
- **ETA** (rough estimate based on actual rate)
- **Last verdict** (the latest row's Buy/Caution/Skip)
- A live **Run log** with one line per row processed

---

## 6. When the run pauses

If your Keepa tokens run out mid-run, the tool will **automatically pause**
and tell you so. Your progress is saved. There are two ways to continue:

- Leave the tool open. As tokens regenerate, click **"▶ Resume previous
  run"** when it appears at the top.
- Close the tool entirely. Re-launch later — the same Resume button will
  appear.

You can also **manually stop** a run using the **"⏹ Stop run"** button.
It checkpoints at the next row boundary (within ~15 seconds) so nothing is
lost.

---

## 7. Reading the report

When the run finishes, the **"4. Download report"** section appears with:

- A blue **Download** button → saves the report as a CSV.
- A **preview table** in the browser showing the most useful columns (UPC,
  ASIN, recommended sell price, profit, ROI, BSR%, viability label, notes).
- An **expandable "Show all columns"** for the full table.

The first row of the downloaded CSV is a **column-help row** in plain
English. To skip it:

- **Excel**: just delete row 2.
- **Google Sheets**: same — delete row 2.
- **pandas**: `pd.read_csv("report.csv", skiprows=[1])`.

If you don't want it at all, uncheck **"Include column-help row"** in the
sidebar before running.

### What the labels mean

| Label | What you do |
|---|---|
| `Buy` | Hits all your thresholds (≥30% ROI, ≥$1 profit, ≤2% BSR, not dominated, ≤15 sellers). Source it. |
| `Caution — thin margin` | Profitable, but under your 30% ROI floor. Probably skip unless you have very low overhead. |
| `Caution — crowded` | Profitable, but >15 FBA sellers — you might never win the buy box. |
| `Skip — Sell price below cost` | Market price is lower than what you paid. Don't source. |
| `Skip — Amazon dominant` | Amazon held the buy box ≥70% of the last 90 days. You won't compete. |
| `Skip — Brand dominant (heuristic)` | One 3P seller looking like the brand owns the buy box. *Heuristic — verify manually.* |
| `Skip — Slow seller` | BSR worse than 2% of category — too slow. |
| `Pass` | Not profitable at all. |

---

## 8. Where files live

Everything is under your home folder so it survives across launches:

- **macOS**: `~/.sa-rebuild/`
- **Windows**: `C:\Users\<you>\.sa-rebuild\`

Inside:

- `settings.json` — your Keepa key
- `cache/keepa.sqlite` — 24h cache of Keepa responses (so re-runs of the
  same products cost zero tokens)
- `state/` — checkpoint files for resume
- `output/` — every report you've generated, by timestamp
- `input/` — copies of CSVs you uploaded

Safe to delete `cache/` to free space — it'll just re-fetch on next use.
**Don't delete `settings.json`** unless you want to re-enter your key.

---

## 9. Troubleshooting

**The browser didn't open.**
Look at the terminal window. You'll see a line like
`Local URL: http://127.0.0.1:54321`. Copy that into any browser.

**"Keepa API key missing" error.**
Click in the **sidebar**, paste your key, press Enter.

**Run is stuck on one product for many minutes.**
Normal — Keepa's bucket is empty and the tool is waiting for tokens to
regenerate. Watch "Tokens left" in the progress bar. Each token takes 1
minute to regenerate.

**My output numbers don't match SellerAmp.**
Two common causes:

1. **Variation children**: SellerAmp shows the parent's combined sales
   (e.g. 1630/mo across 269 sizes). This tool shows the per-child number
   (e.g. 50/mo for the specific size you scanned), which is more accurate
   for your sourcing decision. Set the sidebar slider to `>0` to also
   fetch parent + sibling variations.
2. **Apparel referral fee**: Amazon charges 17% (not 15%) for clothing >$15.
   Already pre-configured.

**I want to share my results with someone else.**
The downloaded CSV has everything. Send it directly. They don't need this
tool to read it.

**The app crashed on launch.**
Restart it (close the terminal window, double-click the app again). If it
keeps failing, capture the terminal output and open a GitHub issue.

---

## 10. Privacy

- Your **Keepa API key** is stored locally in `~/.sa-rebuild/settings.json`.
  It never leaves your machine except in API calls **you** make to
  `keepa.com` (which is the whole point).
- Your **input CSVs** are stored locally in `~/.sa-rebuild/input/`.
- **Output reports** are stored locally in `~/.sa-rebuild/output/`.
- No telemetry, no analytics, no remote logging. The tool runs entirely
  offline except for the Keepa API calls.
