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

A subdomain `tools.centrallinegroup.com` that redirects visitors to
your Streamlit app. Your main domain and Neo email are completely
unaffected — email uses MX records, the redirect uses its own record,
they are independent.

> **Note on custom domains:** Streamlit Community Cloud (free plan)
> does not support true custom domains — there is no "Custom domain"
> field in app settings. The approach below uses Namecheap's URL
> redirect feature. After the redirect the browser address bar will
> show `centralline-tools.streamlit.app`, but the link
> `tools.centrallinegroup.com` will work and take people to the right
> place. True domain masking requires Streamlit's paid Teams plan or
> self-hosting.

---

### Step 1 — Add a URL Redirect Record in Namecheap

1. Log in to **[namecheap.com](https://namecheap.com)**
2. Click **"Domain List"** in the left sidebar
3. Find `centrallinegroup.com` → click **"Manage"**
4. Click the **"Advanced DNS"** tab
5. Scroll to **"Host Records"** → click **"Add New Record"**
6. Fill in the fields:

   | Field | Value |
   |---|---|
   | **Type** | `URL Redirect Record` |
   | **Host** | `tools` |
   | **Value** | `https://centralline-tools.streamlit.app` |
   | **Redirect type** | `Unmasked` |
   | **TTL** | `Automatic` |

7. Click the **green checkmark** to save

If you previously added a CNAME record for `tool`, delete it — only
keep this URL Redirect Record for `tools`.

---

### Step 2 — Wait for DNS propagation

DNS changes take between **5 minutes and 24 hours** to spread globally
(usually under 30 minutes). Check progress at
**[dnschecker.org](https://dnschecker.org)**:

1. Type `tools.centrallinegroup.com` in the search box at the top
2. Select **A** in the record-type dropdown next to it
3. Click the blue **Search** button

You'll see a world map with dots — green means that location can see
your DNS record, red/grey means it hasn't propagated there yet.

Once propagated, visiting `tools.centrallinegroup.com` will redirect
to `centralline-tools.streamlit.app`.

---

## Summary

| Task | Where |
|---|---|
| Deploy the app | [share.streamlit.io](https://share.streamlit.io) |
| Add URL Redirect Record | Namecheap → Domain List → Manage → Advanced DNS |
| Check DNS propagation | [dnschecker.org](https://dnschecker.org) — type A record for `tools.centrallinegroup.com` |
