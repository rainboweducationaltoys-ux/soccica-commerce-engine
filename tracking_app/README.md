# SOC Tracking app

Standalone Flask + Postgres app for `track.soccica.ae`. Fully independent from the
main `src/` pipeline — no shared imports, its own `requirements.txt`.

Everything below is a set of manual steps for **you** to run — nothing here is
executed automatically.

## 1. Register the Shopify webhook

This app registers itself against your **existing custom app** (the one whose
`SHOPIFY_CLIENT_ID`/`SHOPIFY_CLIENT_SECRET` already live in the main project's
`.env`), via the GraphQL Admin API — not the legacy Notifications-page webhook UI.
That means the webhook's signing secret is simply **the same value as your existing
`SHOPIFY_CLIENT_SECRET`** — nothing new to generate.

Run this once the app is deployed and `track.soccica.ae` resolves (step 7 depends on
steps 2–6 below being done first). Use `curl` or Shopify's built-in GraphiQL app
explorer in admin:

```bash
curl -X POST "https://<your-shop>.myshopify.com/admin/api/2026-07/graphql.json" \
  -H "X-Shopify-Access-Token: <your app's access token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "mutation { webhookSubscriptionCreate(topic: ORDERS_CREATE, webhookSubscription: {uri: \"https://track.soccica.ae/webhooks/orders-create\", format: JSON}) { webhookSubscription { id } userErrors { field message } } }"
  }'
```

Set on Render (see step 3): `SHOPIFY_WEBHOOK_SECRET` = the same value as your main
project's `SHOPIFY_CLIENT_SECRET`.

Check the response's `userErrors` array is empty. If you ever need to re-point the
webhook at a different URL, delete the old subscription first
(`webhookSubscriptionDelete`) rather than creating a duplicate.

## 2. Push to GitHub

Render deploys from a Git repo. You can keep `tracking_app/` inside the same
`soccica-amazon-importer` repo — Render supports deploying from a subdirectory of a
monorepo via the "Root Directory" setting (step 4), so there's no need for a
separate repo.

```bash
git push origin main
```

(or whichever remote/branch you use — this project doesn't have a GitHub remote
configured yet, so you'll need to create one first: create a repo on GitHub, then
`git remote add origin <url>` and push.)

## 3. Create the Render Postgres instance

In the Render dashboard: **New → PostgreSQL**. Give it a name (e.g.
`soccica-tracking-db`). Free/Starter tier is fine for this traffic level. Once
created, Render shows you an **Internal Database URL** and **External Database
URL** — you don't need to copy either by hand (see step 4).

## 4. Create the Render Web Service

**New → Web Service** → connect the GitHub repo from step 2.

- **Root Directory**: `tracking_app`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: leave blank (Render reads the `Procfile`) or set explicitly to
  `gunicorn app:app`
- **Environment**: set these env vars:
  - `ADMIN_USERNAME` — pick a username
  - `ADMIN_PASSWORD` — pick a strong password
  - `SECRET_KEY` — any long random string (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`)
  - `SHOPIFY_WEBHOOK_SECRET` — same value as the main project's `SHOPIFY_CLIENT_SECRET`
- **Link the database**: in the web service's Environment tab, use Render's "Add
  from Database" option and pick the Postgres instance from step 3 — this
  auto-injects `DATABASE_URL` for you, no manual copy-pasting.

Deploy. Check the deploy logs for `CREATE TABLE` errors (there shouldn't be any —
`db.initialize_database()` runs automatically on app startup).

## 5. Add the custom domain

In the web service → **Settings → Custom Domains → Add Custom Domain** → enter
`track.soccica.ae`. Render will show you a target hostname (something like
`your-service.onrender.com`) to use in a CNAME record.

## 6. Add the DNS record in Shopify admin

Shopify manages `soccica.ae`'s DNS since the domain is connected there. In Shopify
admin: **Settings → Domains → soccica.ae → DNS settings** (or "Manage DNS records")
→ **Add CNAME record**:
- Host: `track`
- Points to: the value Render gave you in step 5
- TTL: default is fine

DNS propagation can take anywhere from a few minutes to a few hours. Render will
show the custom domain as "Verified" once it detects the CNAME resolving correctly,
and will auto-provision an SSL certificate for it.

## 7. Register the webhook (back to step 1)

Once `track.soccica.ae` resolves and shows the tracking app (test by visiting
`https://track.soccica.ae/track/anything` — you should see the "kod bulunamadı"
page, not a connection error), run the `curl` command from step 1.

## Testing it end-to-end

1. Place a real (or test-mode) order in your Shopify store.
2. Check Render's logs for the web service — you should see the webhook POST land
   within a few seconds.
3. Query the `orders` table (Render dashboard → your Postgres instance → "Connect"
   → use the provided `psql` command) to confirm a row was inserted with a fresh
   `soc_tracking_code`.
4. Visit `https://track.soccica.ae/track/<that code>` — should show "Order
   Confirmed" and the timeline.
5. Log into `/admin` with `ADMIN_USERNAME`/`ADMIN_PASSWORD`, open that order, advance
   its status, confirm the public tracking page updates.

## What's never shown on the public `/track/<code>` page

`internal_notes`, the Shopify order id/number, customer name/email, and anything
Amazon-related. The page only ever renders the SOC code, current status, and the
public timeline (status + optional public note + date).
