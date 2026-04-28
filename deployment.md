# Deployment Guide

How to deploy sa-rebuild to Streamlit Community Cloud and connect it to
your custom domain (centrallinegroup.com) via Namecheap.

---

## Part 1 — Deploy to Streamlit Community Cloud

### Step 1 — Create a Streamlit account

1. Go to **[share.streamlit.io](https://share.streamlit.io)**
2. Click **"Sign up"** → choose **"Continue with GitHub"**
3. Authorize Streamlit to access your GitHub account
4. You'll land on your Streamlit dashboard

---

### Step 2 — Deploy the app

1. Click **"New app"** (top right)
2. Fill in the form:
   - **Repository:** `Emanoid/selleramp_rebuild`
   - **Branch:** `main`
   - **Main file path:** `src/sa_rebuild/web/app.py`
3. Leave **App URL** as the auto-generated default for now (you'll replace it with your domain later)
4. Click **"Deploy"**

Streamlit will install your `requirements.txt` and boot the app. First
deploy takes 2–4 minutes. You'll see a live log. When it turns green you
get a URL like:

```
https://centralline-tools.streamlit.app
```

**Test it** — open that URL, paste your Keepa key in the sidebar, upload
the template CSV, and confirm it works before touching DNS.

---

### Step 3 — How to redeploy after code changes

Every time you push to `main` on GitHub, Streamlit **automatically
redeploys** — no action needed. You'll see a "Source code changed"
spinner in the app briefly while it restarts.

---

## Part 2 — Namecheap subdomain + DNS

### What you'll create

A subdomain like `tool.centrallinegroup.com` (or any prefix you choose)
that points to your Streamlit app. Your main domain and Neo email are
completely unaffected — email uses MX records, web uses CNAME, they are
independent.

---

### Step 1 — Pick your subdomain prefix

Decide what you want before the dot. Examples:

- `tool.centrallinegroup.com`
- `sourcing.centrallinegroup.com`
- `fba.centrallinegroup.com`

---

### Step 2 — Get your Streamlit CNAME target

After deploying in Part 1, your app URL looks like:

```
https://centralline-tools.streamlit.app
```

The CNAME target is that hostname **without** `https://`:

```
centralline-tools.streamlit.app
```

Keep this handy for the next step.

---

### Step 3 — Add the CNAME record in Namecheap

1. Log in to **[namecheap.com](https://namecheap.com)**
2. Click **"Domain List"** in the left sidebar
3. Find `centrallinegroup.com` → click **"Manage"**
4. Click the **"Advanced DNS"** tab
5. Scroll to **"Host Records"** → click **"Add New Record"**
6. Fill in the fields:

   | Field | Value |
   |---|---|
   | **Type** | `CNAME Record` |
   | **Host** | `tool` *(or whichever prefix you chose — just the part before the dot)* |
   | **Value** | `centralline-tools.streamlit.app` *(your actual Streamlit URL)* |
   | **TTL** | `Automatic` |

7. Click the **green checkmark** to save

---

### Step 4 — Register the custom domain in Streamlit

Streamlit needs to know your domain is pointing at it:

1. Go to your app on [share.streamlit.io](https://share.streamlit.io)
2. Click the **three-dot menu** (⋮) next to your app → **"Settings"**
3. Go to the **"General"** tab → find **"Custom domain"**
4. Enter your full subdomain: `tool.centrallinegroup.com`
5. Click **"Save"**

---

### Step 5 — Wait for DNS propagation

DNS changes take between **5 minutes and 24 hours** to spread globally
(usually under 30 minutes). Check progress at
**[dnschecker.org](https://dnschecker.org)** — type in your subdomain
and watch for green checkmarks across locations.

Once propagated, visiting `tool.centrallinegroup.com` loads your
Streamlit app with a valid HTTPS certificate (Streamlit handles SSL
automatically — nothing extra needed).

---

## Summary

| Task | Where |
|---|---|
| Deploy the app | [share.streamlit.io](https://share.streamlit.io) |
| Add CNAME record | Namecheap → Domain List → Manage → Advanced DNS |
| Register custom domain | Streamlit app → ⋮ → Settings → General |
| Check DNS propagation | [dnschecker.org](https://dnschecker.org) |
