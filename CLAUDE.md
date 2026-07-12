# Soccica Commerce Engine

## Project Purpose

Soccica automates importing profitable products from Amazon into Shopify with minimal
human intervention. Input is a plain list of Amazon ASINs (sourced externally via an
ASIN Spotlight tool — not something this app generates). For each ASIN, the system:

1. Checks Amazon US, UK, and Germany.
2. Verifies stock and UAE delivery eligibility (not just "in stock" — must actually be
   shippable to Dubai).
3. Calculates landed cost = product price + shipping/import charges (Amazon sometimes
   shows these as one combined figure — must not be double-counted).
4. Picks the marketplace with the lowest valid landed cost.
5. Calculates the Shopify selling price: landed cost + currency buffer + return risk +
   payment fee + UAE last-mile cost + target margin.
6. Extracts content (title, brand, bullets, description, images) from the winning
   marketplace page.
7. Optionally rewrites content with AI for SEO.
8. Classifies into collections/tags, checks for duplicates.
9. Creates the product in Shopify as a **DRAFT** (never auto-published) with SKU = ASIN
   and metafields.
10. Tracks every stage in SQLite (`data/soccica.db`) as the single source of truth, with
    a status state machine and resume-on-crash behavior.

**Scope boundary (confirmed with project owner):** this app does not do ASIN discovery
(external tool) and does not do real-time per-order price re-checking — price/stock
re-verification is periodic and manually triggered, not automated on every Shopify
order. Don't build automated order-time re-pricing unless explicitly asked.

**Long-term vision:** grow from an Amazon-only importer into a multi-source (Walmart,
Target, eBay, AliExpress, Temu...) commerce automation platform managing 100,000+
products, with scheduled sync, real-time dashboard, and multi-threaded processing.
Keep this scale in mind architecturally (SQLite is single-writer and will need to
become a queue/Postgres setup before heavy parallelism), but don't over-build for it
now — current priority is a solid single-marketplace-set pipeline.

## Architecture / Data Flow

```
input/asin_spotlight.txt (or input/test_asins.txt when DRY_RUN=true)
  -> SQLite (products table, status=pending)
  -> run_pipeline.py: scrape US/UK/DE via Playwright (product_engine.scrape_complete_offer)
     -> select_best_offer() picks lowest landed cost among eligible offers
     -> pricing_engine.calculate_selling_price()
     -> product_store.save_scraped_product() persists full content to SQLite,
        status=ready_for_shopify
  -> publish_final_products.py: product_store.get_ready_products() reads full
     product rows straight from SQLite (no CSV in the loop)
     -> ai_rewrite.py (optional), collections_engine.py, duplicate_engine.py
     -> if DRY_RUN=true: payload printed + written to output/dry_run/<asin>.json,
        no Shopify write, status stays ready_for_shopify
     -> else: shopify_api.py creates draft, sets SKU via inventoryItemUpdate, sets
        metafields, mark_published() in SQLite, status=published
  -> ./run.sh / run_all.py ties the above into one command
```

Key files: `src/run_pipeline.py`, `src/publish_final_products.py`,
`src/product_store.py` (SQLite read/write helpers, incl. `migrate_product_table()`),
`src/database.py` (schema + status machine), `src/product_engine.py` (per-ASIN
scrape), `src/pricing_engine.py`, `src/shopify_api.py`, `src/collections_engine.py`,
`src/duplicate_engine.py`, `src/ai_rewrite.py`, `src/metafields_engine.py`.

Status values: `pending`, `processing`, `retry`, `ready_for_shopify`, `published`,
`skipped`, `error`. If the process is killed mid-run, products stuck in `processing`
move back to `retry` on next start (`recover_processing_products()`).

**Gotcha:** `product_store.migrate_product_table()` adds the content columns
(`brand`, `bullets_json`, `images_json`, etc.) on top of the base schema from
`database.initialize_database()`. Both `run_pipeline.py` and
`publish_final_products.py` call it right after `initialize_database()` in `main()`
— if you add a new script that touches the `products` table directly, call it there
too, or `save_scraped_product()` will fail with `no such column: ...` on a fresh DB.

## Current Known Gaps (updated after SQLite-refactor + DRY_RUN work)

- **Done:** `run_pipeline.py` now calls `product_store.save_scraped_product()`
  (brand, bullets, description, images, availability, shipping/import fields all
  persisted), followed by `update_product_status(status="ready_for_shopify")`.
  Mid-path CSV writes (`all_marketplace_offers.csv`, `final_products.csv`) are gated
  behind `EXPORT_CSV=true` (default off); `pipeline_errors.csv` still writes
  unconditionally for debugging.
- **Done:** `publish_final_products.py` now reads full product content via
  `product_store.get_ready_products()` instead of `pd.read_csv(final_products.csv)`.
  `marketplace` is the raw code (`US`/`UK`/`DE`) — `collections_engine.get_marketplace_tag()`
  already maps that directly, no `marketplace_name` column needed.
- **Done:** `DRY_RUN` sandbox mode exists (see below). `input/test_asins.txt` holds
  3 sample ASINs for dry-run scraping batches.
- No `.gitignore`, not a git repo yet. `.env` (contains Shopify/OpenAI secrets) and
  `data/soccica.db` currently travel inside backup zips — needs fixing before this
  becomes a habit. Note: this machine's `git` CLI currently needs Xcode Command Line
  Tools installed before `git init` will run (`xcode-select --install`).
- No `logging` module usage anywhere — 200+ raw `print()` calls. Fine for manual runs,
  not fine once a scheduler runs this unattended overnight.
- Several older/exploratory modules (`global_price_engine.py`,
  `select_best_marketplace.py`, `scrape_global_prices.py`, `competitor_analyzer.py`,
  `crawl_store.py`, plus a stray nested `src/src/store_crawler.py`) look superseded by
  the SQLite pipeline — audit before assuming they're still live.
- "Final verification still required" (code exists, untested with real data): SKU
  field via `inventoryItemUpdate`, real metafield writes, AI rewrite with a live API
  key, duplicate-similarity behavior in practice, full `./run.sh` end-to-end run.

## Priority Order (agreed)

1. ~~SQLite-first refactor~~ — **done**: `save_scraped_product()` wired into
   `run_pipeline.py`, `get_ready_products()` wired into `publish_final_products.py`,
   mid-path CSV writes gated behind `EXPORT_CSV`.
2. ~~Add `DRY_RUN` sandbox mode~~ — **done**.
3. Git init + `.gitignore` (`.env`, `data/`, `__pycache__`, `.DS_Store`, `*.zip`).
   Blocked on Xcode Command Line Tools on this machine — see gap above.
4. Run the 5 "final verification required" items against real data.
5. Add file-based logging (`logs/app.log` etc.) before considering a scheduler.
6. Clean up dead/duplicate modules.
7. Harden retry/CAPTCHA handling before adding parallel workers.
8. Dashboard, then scheduler, then parallel processing / additional marketplaces,
   then price-stock sync — in that order.

Explicitly deprioritized for now: Keepa integration (rejected — current scraping
already covers this, price checks are manual/periodic so a separate price-monitoring
API isn't needed), automated order-time re-pricing, multi-source connectors (Walmart
etc. — future vision, not current work).

## Manual Test Sequence (run after any pipeline change)

1. `python src/test_database.py` — SQLite read/write sanity check.
2. `python src/test_shopify.py` — Shopify API connection check.
3. `python src/test_create_product.py` — confirms Shopify write access (delete the
   resulting test draft from Shopify admin afterward).
4. Inspect SQLite directly: `sqlite3 data/soccica.db` →
   `SELECT asin, status, brand, images_json, description FROM products LIMIT 5;` —
   confirms content fields are actually populated after a pipeline run.
5. Run `python src/run_pipeline.py` with `DRY_RUN=true` — uses `input/test_asins.txt`
   (2-3 ASINs) instead of the full `asin_spotlight.txt` batch.
6. Run `publish_final_products.py` with `DRY_RUN=true`, inspect
   `output/dry_run/<asin>.json` payloads before anything touches live Shopify.
7. One real run with `DRY_RUN=false`, `PUBLISH_LIMIT=1` — check the Shopify draft by
   hand (SKU = ASIN, images present, metafields populated).
8. Check errors via SQLite: `SELECT asin, error, status FROM products WHERE status='error';`
9. Kill the pipeline mid-run (Ctrl+C) and restart it — confirm `processing` rows move
   to `retry` and the run resumes instead of restarting from scratch.
