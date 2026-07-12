import json
from typing import Any

from database import get_connection, utc_now


PRODUCT_COLUMNS: dict[str, str] = {
    "brand": "TEXT",
    "availability": "TEXT",
    "shipping_to_uae": "TEXT",
    "import_fees": "TEXT",
    "item_price_aed": "REAL",
    "extra_charges_aed": "REAL",
    "charges_type": "TEXT",
    "bullets_json": "TEXT",
    "description": "TEXT",
    "images_json": "TEXT",
    "ai_title": "TEXT",
    "ai_bullets_json": "TEXT",
    "ai_description": "TEXT",
    "seo_title": "TEXT",
    "meta_description": "TEXT",
    "product_type": "TEXT",
    "tags_json": "TEXT",
    "collections_json": "TEXT",
    "duplicate_reason": "TEXT",
    "matched_asin": "TEXT",
    "similarity": "REAL",
}


def safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def json_text(value: Any) -> str:
    if value is None:
        value = []

    return json.dumps(
        value,
        ensure_ascii=False,
    )


def parse_json_list(value: Any) -> list[Any]:
    text = safe_text(value)

    if not text:
        return []

    try:
        parsed = json.loads(text)

        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass

    return []


def get_existing_product_columns() -> set[str]:
    with get_connection() as connection:
        rows = connection.execute(
            "PRAGMA table_info(products)"
        ).fetchall()

    return {
        str(row["name"])
        for row in rows
    }


def migrate_product_table() -> list[str]:
    existing_columns = get_existing_product_columns()
    added_columns: list[str] = []

    with get_connection() as connection:
        for column_name, column_type in (
            PRODUCT_COLUMNS.items()
        ):
            if column_name in existing_columns:
                continue

            connection.execute(
                f"""
                ALTER TABLE products
                ADD COLUMN {column_name} {column_type}
                """
            )

            added_columns.append(column_name)

    return added_columns


def save_scraped_product(
    product: dict[str, Any],
) -> None:
    asin = safe_text(
        product.get("asin")
    ).upper()

    if not asin:
        raise ValueError(
            "Ürün kaydı için ASIN zorunludur."
        )

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE products
            SET
                title = ?,
                brand = ?,
                marketplace = ?,
                source_url = ?,
                availability = ?,
                shipping_to_uae = ?,
                import_fees = ?,
                item_price_aed = ?,
                extra_charges_aed = ?,
                charges_type = ?,
                landed_cost_aed = ?,
                shopify_price_aed = ?,
                bullets_json = ?,
                description = ?,
                images_json = ?,
                error = '',
                updated_at = ?
            WHERE asin = ?
            """,
            (
                safe_text(product.get("title")),
                safe_text(product.get("brand")),
                safe_text(product.get("marketplace")),
                safe_text(product.get("source_url")),
                safe_text(product.get("availability")),
                safe_text(product.get("shipping_to_uae")),
                safe_text(product.get("import_fees")),
                float(
                    product.get("item_price_aed", 0)
                    or 0
                ),
                float(
                    product.get(
                        "extra_charges_aed",
                        0,
                    )
                    or 0
                ),
                safe_text(
                    product.get("charges_type")
                ),
                float(
                    product.get(
                        "landed_cost_aed",
                        0,
                    )
                    or 0
                ),
                float(
                    product.get(
                        "shopify_price_aed",
                        0,
                    )
                    or 0
                ),
                json_text(
                    product.get("bullets", [])
                ),
                safe_text(
                    product.get("description")
                ),
                json_text(
                    product.get("images", [])
                ),
                utc_now(),
                asin,
            ),
        )


def save_ai_content(
    asin: str,
    ai_content: dict[str, Any],
) -> None:
    normalized_asin = safe_text(
        asin
    ).upper()

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE products
            SET
                ai_title = ?,
                ai_bullets_json = ?,
                ai_description = ?,
                seo_title = ?,
                meta_description = ?,
                product_type = ?,
                tags_json = ?,
                updated_at = ?
            WHERE asin = ?
            """,
            (
                safe_text(
                    ai_content.get("title")
                ),
                json_text(
                    ai_content.get("bullets", [])
                ),
                safe_text(
                    ai_content.get("description")
                ),
                safe_text(
                    ai_content.get("seo_title")
                ),
                safe_text(
                    ai_content.get(
                        "meta_description"
                    )
                ),
                safe_text(
                    ai_content.get("product_type")
                ),
                json_text(
                    ai_content.get("tags", [])
                ),
                utc_now(),
                normalized_asin,
            ),
        )


def save_collection_tags(
    asin: str,
    tags: list[str],
) -> None:
    normalized_asin = safe_text(
        asin
    ).upper()

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE products
            SET
                collections_json = ?,
                updated_at = ?
            WHERE asin = ?
            """,
            (
                json_text(tags),
                utc_now(),
                normalized_asin,
            ),
        )


def save_duplicate_result(
    asin: str,
    duplicate_result: dict[str, Any],
) -> None:
    normalized_asin = safe_text(
        asin
    ).upper()

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE products
            SET
                duplicate_reason = ?,
                matched_asin = ?,
                similarity = ?,
                updated_at = ?
            WHERE asin = ?
            """,
            (
                safe_text(
                    duplicate_result.get("reason")
                ),
                safe_text(
                    duplicate_result.get(
                        "matched_asin"
                    )
                ),
                float(
                    duplicate_result.get(
                        "similarity",
                        0,
                    )
                    or 0
                ),
                utc_now(),
                normalized_asin,
            ),
        )


def get_ready_products(
    limit: int = 100,
) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM products
            WHERE status = 'ready_for_shopify'
            ORDER BY updated_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    products: list[dict[str, Any]] = []

    for row in rows:
        product = dict(row)

        product["bullets"] = parse_json_list(
            product.get("bullets_json")
        )

        product["images"] = parse_json_list(
            product.get("images_json")
        )

        product["ai_bullets"] = parse_json_list(
            product.get("ai_bullets_json")
        )

        product["ai_tags"] = parse_json_list(
            product.get("tags_json")
        )

        product["collection_tags"] = parse_json_list(
            product.get("collections_json")
        )

        products.append(product)

    return products


def get_product_by_asin(
    asin: str,
) -> dict[str, Any] | None:
    normalized_asin = safe_text(
        asin
    ).upper()

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM products
            WHERE asin = ?
            """,
            (normalized_asin,),
        ).fetchone()

    if not row:
        return None

    product = dict(row)

    product["bullets"] = parse_json_list(
        product.get("bullets_json")
    )

    product["images"] = parse_json_list(
        product.get("images_json")
    )

    product["ai_bullets"] = parse_json_list(
        product.get("ai_bullets_json")
    )

    product["ai_tags"] = parse_json_list(
        product.get("tags_json")
    )

    product["collection_tags"] = parse_json_list(
        product.get("collections_json")
    )

    return product