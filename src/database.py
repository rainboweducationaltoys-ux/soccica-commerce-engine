import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_FILE = BASE_DIR / "data" / "soccica.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    DATABASE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row

    return connection


def initialize_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                asin TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                title TEXT,
                marketplace TEXT,
                source_url TEXT,
                landed_cost_aed REAL,
                shopify_price_aed REAL,
                shopify_product_id TEXT,
                shopify_variant_id TEXT,
                shopify_handle TEXT,
                error TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS marketplace_offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asin TEXT NOT NULL,
                marketplace TEXT NOT NULL,
                status TEXT,
                source_url TEXT,
                item_price_aed REAL,
                extra_charges_aed REAL,
                landed_cost_aed REAL,
                availability TEXT,
                title TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(asin, marketplace)
            )
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_products_status
            ON products(status)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_offers_asin
            ON marketplace_offers(asin)
            """
        )


def add_asin(asin: str) -> None:
    asin = asin.strip().upper()

    if not asin:
        return

    now = utc_now()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO products (
                asin,
                status,
                created_at,
                updated_at
            )
            VALUES (?, 'pending', ?, ?)
            ON CONFLICT(asin) DO NOTHING
            """,
            (
                asin,
                now,
                now,
            ),
        )


def add_asins(asins: list[str]) -> int:
    before_count = count_products()

    for asin in asins:
        add_asin(asin)

    after_count = count_products()

    return after_count - before_count


def count_products(
    status: str | None = None,
) -> int:
    with get_connection() as connection:
        if status:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM products
                WHERE status = ?
                """,
                (status,),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM products
                """
            ).fetchone()

    return int(row["total"])


def get_next_pending_asins(
    limit: int = 100,
) -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT asin
            FROM products
            WHERE status IN ('pending', 'retry')
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        str(row["asin"])
        for row in rows
    ]


def update_product_status(
    asin: str,
    status: str,
    error: str = "",
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE products
            SET
                status = ?,
                error = ?,
                attempt_count = attempt_count + 1,
                updated_at = ?
            WHERE asin = ?
            """,
            (
                status,
                error,
                utc_now(),
                asin.strip().upper(),
            ),
        )


def save_marketplace_offer(
    offer: dict[str, Any],
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO marketplace_offers (
                asin,
                marketplace,
                status,
                source_url,
                item_price_aed,
                extra_charges_aed,
                landed_cost_aed,
                availability,
                title,
                error,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(asin, marketplace)
            DO UPDATE SET
                status = excluded.status,
                source_url = excluded.source_url,
                item_price_aed = excluded.item_price_aed,
                extra_charges_aed = excluded.extra_charges_aed,
                landed_cost_aed = excluded.landed_cost_aed,
                availability = excluded.availability,
                title = excluded.title,
                error = excluded.error,
                created_at = excluded.created_at
            """,
            (
                offer.get("asin", ""),
                offer.get("marketplace", ""),
                offer.get("status", ""),
                offer.get("source_url", ""),
                offer.get("item_price_aed", 0),
                offer.get("extra_charges_aed", 0),
                offer.get("landed_cost_aed", 0),
                offer.get("availability", ""),
                offer.get("title", ""),
                offer.get("error", ""),
                utc_now(),
            ),
        )


def save_selected_product(
    asin: str,
    title: str,
    marketplace: str,
    source_url: str,
    landed_cost_aed: float,
    shopify_price_aed: float,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE products
            SET
                status = 'ready_for_shopify',
                title = ?,
                marketplace = ?,
                source_url = ?,
                landed_cost_aed = ?,
                shopify_price_aed = ?,
                error = '',
                updated_at = ?
            WHERE asin = ?
            """,
            (
                title,
                marketplace,
                source_url,
                landed_cost_aed,
                shopify_price_aed,
                utc_now(),
                asin.strip().upper(),
            ),
        )


def mark_published(
    asin: str,
    product_id: str,
    variant_id: str,
    handle: str,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE products
            SET
                status = 'published',
                shopify_product_id = ?,
                shopify_variant_id = ?,
                shopify_handle = ?,
                error = '',
                updated_at = ?
            WHERE asin = ?
            """,
            (
                product_id,
                variant_id,
                handle,
                utc_now(),
                asin.strip().upper(),
            ),
        )


def is_published(asin: str) -> bool:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT status
            FROM products
            WHERE asin = ?
            """,
            (asin.strip().upper(),),
        ).fetchone()

    return bool(
        row
        and row["status"] == "published"
    )


def get_status_summary() -> dict[str, int]:
    summary = {
        "total": 0,
        "pending": 0,
        "processing": 0,
        "ready_for_shopify": 0,
        "published": 0,
        "skipped": 0,
        "retry": 0,
        "error": 0,
    }

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM products
            GROUP BY status
            """
        ).fetchall()

    for row in rows:
        status = str(row["status"])
        total = int(row["total"])

        summary["total"] += total
        summary[status] = total

    return summary


def reset_database() -> None:
    if DATABASE_FILE.exists():
        DATABASE_FILE.unlink()

    initialize_database()


def recover_processing_products() -> int:
    """
    Önceki çalışma yarıda kaldıysa processing durumundaki
    ürünleri tekrar retry durumuna getirir.
    """
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE products
            SET
                status = 'retry',
                updated_at = ?
            WHERE status = 'processing'
            """,
            (utc_now(),),
        )

        return cursor.rowcount