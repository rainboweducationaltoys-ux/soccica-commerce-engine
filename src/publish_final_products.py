import html
import json
import os
from pathlib import Path
from typing import Any
from metafields_engine import build_product_metafields

import pandas as pd
from dotenv import load_dotenv

from ai_rewrite import rewrite_product_content
from collections_engine import build_collection_tags
from database import (
    get_connection,
    initialize_database,
    mark_published,
    update_product_status,
)
from duplicate_engine import check_local_duplicate
from product_store import (
    get_ready_products,
    migrate_product_table,
)
from shopify_api import (
    create_draft_product_with_price,
    find_product_by_asin,
    set_product_metafields,
)


load_dotenv()


BASE_DIR = Path(__file__).resolve().parent.parent

PUBLISHED_FILE = (
    BASE_DIR
    / "output"
    / "global_prices"
    / "shopify_published.csv"
)

ERROR_FILE = (
    BASE_DIR
    / "output"
    / "global_prices"
    / "shopify_publish_errors.csv"
)

DRY_RUN_DIR = (
    BASE_DIR
    / "output"
    / "dry_run"
)

PUBLISH_LIMIT = int(
    os.getenv("PUBLISH_LIMIT", "1")
)

DRY_RUN = (
    os.getenv("DRY_RUN", "false").lower() == "true"
)


def safe_text(value: Any) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    return str(value).strip()


def build_description_html(
    description: str,
    bullets: list[str],
) -> str:
    parts: list[str] = []

    if bullets:
        parts.append("<h2>Product Highlights</h2>")
        parts.append("<ul>")

        for bullet in bullets:
            parts.append(
                f"<li>{html.escape(bullet)}</li>"
            )

        parts.append("</ul>")

    if description:
        paragraphs = [
            paragraph.strip()
            for paragraph in description.splitlines()
            if paragraph.strip()
        ]

        if paragraphs:
            parts.append(
                "<h2>Product Description</h2>"
            )

            for paragraph in paragraphs:
                parts.append(
                    f"<p>{html.escape(paragraph)}</p>"
                )

    return "".join(parts)


def append_csv_row(
    file_path: Path,
    row: dict[str, Any],
) -> None:
    file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    pd.DataFrame([row]).to_csv(
        file_path,
        mode="a",
        header=not file_path.exists(),
        index=False,
        encoding="utf-8-sig",
    )


def write_dry_run_payload(
    asin: str,
    payload: dict[str, Any],
) -> Path:
    DRY_RUN_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_path = DRY_RUN_DIR / f"{asin}.json"

    file_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return file_path


def save_publish_error(
    asin: str,
    error: str,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE products
            SET
                error = ?,
                attempt_count = attempt_count + 1,
                updated_at = datetime('now')
            WHERE asin = ?
            """,
            (
                error,
                asin,
            ),
        )


def main() -> None:
    initialize_database()
    migrate_product_table()

    products = get_ready_products(
        limit=PUBLISH_LIMIT
    )

    if not products:
        print("Shopify için hazır ürün bulunamadı.")
        return

    print("=" * 70)
    print("SOCCICA SQLITE SHOPIFY PUBLISHER")
    print("=" * 70)
    print("Bu çalışmada yayınlanacak:", len(products))

    success_count = 0
    duplicate_count = 0
    error_count = 0
    dry_run_count = 0

    if DRY_RUN:
        print(
            "DRY_RUN aktif — Shopify'a gerçek yazma "
            "işlemi yapılmayacak."
        )

    for index, db_product in enumerate(
        products,
        start=1,
    ):
        asin = safe_text(db_product.get("asin")).upper()

        print("\n" + "=" * 70)
        print(
            f"Ürün {index}/{len(products)} — {asin}"
        )
        print("=" * 70)

        title = safe_text(db_product.get("title"))
        brand = safe_text(db_product.get("brand"))
        price_text = safe_text(
            db_product.get("shopify_price_aed")
        )

        try:
            price = float(price_text)
        except ValueError:
            price = 0.0

        images = db_product.get("images", [])
        bullets = db_product.get("bullets", [])
        description = safe_text(
            db_product.get("description")
        )
        marketplace = safe_text(
            db_product.get("marketplace")
        )

        missing: list[str] = []

        if not title:
            missing.append("title")

        if price <= 0:
            missing.append("price")

        if not images:
            missing.append("images")

        if missing:
            error_text = (
                "Eksik zorunlu alanlar: "
                + ", ".join(missing)
            )

            save_publish_error(
                asin,
                error_text,
            )

            append_csv_row(
                ERROR_FILE,
                {
                    "asin": asin,
                    "title": title,
                    "error": error_text,
                },
            )

            print(error_text)
            error_count += 1
            continue

        try:
            local_duplicate = check_local_duplicate(
                asin=asin,
                title=title,
            )

            if local_duplicate["is_duplicate"]:
                if DRY_RUN:
                    print(
                        "[DRY RUN] Durum değiştirilmedi "
                        "(ready_for_shopify olarak kalıyor)."
                    )
                else:
                    update_product_status(
                        asin=asin,
                        status="skipped",
                        error=(
                            "Duplicate: "
                            + local_duplicate["reason"]
                        ),
                    )

                append_csv_row(
                    PUBLISHED_FILE,
                    {
                        "asin": asin,
                        "shopify_product_id":
                            local_duplicate.get(
                                "shopify_product_id",
                                "",
                            ),
                        "shopify_variant_id": "",
                        "title": title,
                        "handle":
                            local_duplicate.get(
                                "shopify_handle",
                                "",
                            ),
                        "status": "SKIPPED",
                        "price_aed": price,
                        "duplicate_found": True,
                        "duplicate_reason":
                            local_duplicate["reason"],
                        "matched_asin":
                            local_duplicate["matched_asin"],
                        "matched_title":
                            local_duplicate["matched_title"],
                        "similarity":
                            local_duplicate["similarity"],
                    },
                )

                print(
                    "SQLite duplicate bulundu, ürün atlandı."
                )
                print(
                    "Sebep:",
                    local_duplicate["reason"],
                )
                print(
                    "Eşleşen ürün:",
                    local_duplicate["matched_title"],
                )
                print(
                    "Benzerlik:",
                    local_duplicate["similarity"],
                )

                duplicate_count += 1
                continue

            existing_product = find_product_by_asin(
                asin
            )

            if existing_product:
                if DRY_RUN:
                    print(
                        "[DRY RUN] Durum değiştirilmedi "
                        "(ready_for_shopify olarak kalıyor)."
                    )
                else:
                    mark_published(
                        asin=asin,
                        product_id=safe_text(
                            existing_product.get("id")
                        ),
                        variant_id="",
                        handle=safe_text(
                            existing_product.get("handle")
                        ),
                    )

                append_csv_row(
                    PUBLISHED_FILE,
                    {
                        "asin": asin,
                        "shopify_product_id":
                            existing_product.get(
                                "id",
                                "",
                            ),
                        "shopify_variant_id": "",
                        "title":
                            existing_product.get(
                                "title",
                                title,
                            ),
                        "handle":
                            existing_product.get(
                                "handle",
                                "",
                            ),
                        "status":
                            existing_product.get(
                                "status",
                                "",
                            ),
                        "price_aed": price,
                        "duplicate_found": True,
                    },
                )

                print(
                    "Shopify mağazasında zaten var; "
                    "duplicate olarak atlandı."
                )

                duplicate_count += 1
                continue

            ai = rewrite_product_content(
                title=title,
                bullets=bullets,
                description=description,
                brand=brand,
                asin=asin,
            )

            title = ai["title"]
            bullets = ai["bullets"]
            description = ai["description"]
            product_type = safe_text(
                ai.get("product_type", "")
            )

            description_html = build_description_html(
                description=description,
                bullets=bullets,
            )

            tags = build_collection_tags(
                title=title,
                bullets=bullets,
                description=description,
                brand=brand,
                product_type=product_type,
                marketplace=marketplace,
                shopify_price_aed=price,
                ai_tags=ai.get("tags", []),
            )

            tags.append(f"ASIN:{asin}")

            if DRY_RUN:
                dry_run_product_id = f"dry-run-{asin}"

                metafields = build_product_metafields(
                    product_id=dry_run_product_id,
                    asin=asin,
                    marketplace=marketplace,
                    source_url=safe_text(
                        db_product.get("source_url")
                    ),
                    landed_cost_aed=float(
                        db_product.get(
                            "landed_cost_aed", 0
                        )
                        or 0
                    ),
                    shopify_price_aed=price,
                    brand=brand,
                    seo_title=ai.get(
                        "seo_title",
                        title,
                    ),
                    meta_description=ai.get(
                        "meta_description",
                        "",
                    ),
                    product_type=ai.get(
                        "product_type",
                        "",
                    ),
                    collections=tags,
                )

                payload = {
                    "asin": asin,
                    "title": title,
                    "description_html": description_html,
                    "vendor": brand or "Soccica",
                    "product_type": product_type,
                    "tags": tags,
                    "image_urls": images[:12],
                    "price": price,
                    "sku": asin,
                    "metafields": metafields,
                }

                dry_run_file = write_dry_run_payload(
                    asin,
                    payload,
                )

                print(
                    "[DRY RUN] Shopify'a gönderilecek veri:"
                )
                print(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                print(
                    "[DRY RUN] Kaydedildi:",
                    dry_run_file,
                )
                print(
                    "[DRY RUN] Durum değiştirilmedi "
                    "(ready_for_shopify olarak kalıyor)."
                )

                dry_run_count += 1
                continue

            product = create_draft_product_with_price(
                title=title,
                description_html=description_html,
                vendor=brand or "Soccica",
                product_type=product_type,
                tags=tags,
                image_urls=images[:12],
                price=price,
                sku=asin,
            )

            variant = product.get("variant", {})

            metafields = build_product_metafields(
                product_id=product["id"],
                asin=asin,
                marketplace=marketplace,
                source_url=safe_text(
                    db_product.get("source_url")
                ),
                landed_cost_aed=float(
                    db_product.get("landed_cost_aed", 0) or 0
                ),
                shopify_price_aed=price,
                brand=brand,
                seo_title=ai.get(
                    "seo_title",
                    title,
                ),
                meta_description=ai.get(
                    "meta_description",
                    "",
                ),
                product_type=ai.get(
                    "product_type",
                    "",
                ),
                collections=tags,
            )

            set_product_metafields(
                metafields
            )

            mark_published(
                asin=asin,
                product_id=product["id"],
                variant_id=safe_text(
                    variant.get("id")
                ),
                handle=product["handle"],
            )

            append_csv_row(
                PUBLISHED_FILE,
                {
                    "asin": asin,
                    "shopify_product_id": product["id"],
                    "shopify_variant_id":
                        variant.get("id", ""),
                    "title": product["title"],
                    "handle": product["handle"],
                    "status": product["status"],
                    "price_aed":
                        variant.get("price", price),
                    "source_marketplace": marketplace,
                    "duplicate_found": False,
                },
            )

            print("Shopify DRAFT oluşturuldu.")
            print("Başlık:", product["title"])
            print("Fiyat:", price, "AED")

            success_count += 1

        except Exception as error:
            error_text = str(error)

            save_publish_error(
                asin,
                error_text,
            )

            append_csv_row(
                ERROR_FILE,
                {
                    "asin": asin,
                    "title": title,
                    "error": error_text,
                },
            )

            print("Shopify hatası:", error_text)
            error_count += 1

    print("\n" + "=" * 70)
    print("SHOPIFY PARTİSİ TAMAMLANDI")
    print("=" * 70)
    print("Yeni oluşturulan:", success_count)
    print("Duplicate bulunan:", duplicate_count)
    print("Hatalı:", error_count)

    if DRY_RUN:
        print(
            "Dry-run (gerçek gönderim yapılmadı):",
            dry_run_count,
        )


if __name__ == "__main__":
    main()