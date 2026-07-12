# Dry-run / sandbox mode

`DRY_RUN` lets you exercise the pipeline without touching the real Shopify
store or burning through the full Amazon ASIN batch.

## Turning it on

Set in `.env`:

```
DRY_RUN=true
```

or export it for a single run:

```
DRY_RUN=true ./run.sh
```

## What changes

**`run_pipeline.py`** — Amazon scraping still runs for real (it's read-only),
but the ASIN batch is read from `input/test_asins.txt` instead of
`input/asin_spotlight.txt`, if that file exists. Edit `input/test_asins.txt`
to change which ASINs get scraped in dry-run mode.

**`publish_final_products.py`** — no real Shopify writes happen. Instead of
calling `create_draft_product_with_price`, `set_product_metafields`, and
`mark_published`, each product's full payload (title, price, images, tags,
metafields) is printed to the console and written to
`output/dry_run/<asin>.json` for inspection. The product's SQLite status is
left as `ready_for_shopify` (not `published` or `skipped`), so the same test
ASINs can be re-run through dry-run repeatedly, and a real run can still pick
them up afterward.

## Turning it off

Set `DRY_RUN=false` (or remove the line) in `.env` before a real run.
`input/test_asins.txt` and `output/dry_run/` are untouched by real runs —
they're only ever read/written in dry-run mode.
