import os
import re
from difflib import SequenceMatcher
from typing import Any

from dotenv import load_dotenv

from database import get_connection, is_published


load_dotenv()


TITLE_SIMILARITY_THRESHOLD = float(
    os.getenv(
        "DUPLICATE_TITLE_THRESHOLD",
        "0.94",
    )
)


def safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def normalize_title(title: str) -> str:
    text = safe_text(title).lower()

    # Noktalama işaretlerini boşluğa çevir.
    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text,
    )

    # Gereksiz genel kelimeleri çıkar.
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "new",
        "pack",
        "set",
        "pcs",
        "pieces",
        "piece",
    }

    words = [
        word
        for word in text.split()
        if word not in stop_words
    ]

    return " ".join(words)


def title_similarity(
    first_title: str,
    second_title: str,
) -> float:
    first = normalize_title(first_title)
    second = normalize_title(second_title)

    if not first or not second:
        return 0.0

    if first == second:
        return 1.0

    return SequenceMatcher(
        None,
        first,
        second,
    ).ratio()


def find_similar_published_product(
    asin: str,
    title: str,
) -> dict[str, Any] | None:
    normalized_asin = safe_text(
        asin
    ).upper()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                asin,
                title,
                shopify_product_id,
                shopify_handle
            FROM products
            WHERE
                status = 'published'
                AND asin != ?
                AND title IS NOT NULL
                AND title != ''
            """,
            (normalized_asin,),
        ).fetchall()

    best_match: dict[str, Any] | None = None
    best_score = 0.0

    for row in rows:
        existing_title = safe_text(
            row["title"]
        )

        score = title_similarity(
            title,
            existing_title,
        )

        if score > best_score:
            best_score = score

            best_match = {
                "asin": safe_text(
                    row["asin"]
                ),
                "title": existing_title,
                "shopify_product_id": safe_text(
                    row["shopify_product_id"]
                ),
                "shopify_handle": safe_text(
                    row["shopify_handle"]
                ),
                "similarity": round(
                    score,
                    4,
                ),
            }

    if (
        best_match
        and best_score
        >= TITLE_SIMILARITY_THRESHOLD
    ):
        return best_match

    return None


def check_local_duplicate(
    asin: str,
    title: str,
) -> dict[str, Any]:
    normalized_asin = safe_text(
        asin
    ).upper()

    if is_published(normalized_asin):
        return {
            "is_duplicate": True,
            "reason": "asin_already_published",
            "matched_asin": normalized_asin,
            "matched_title": title,
            "similarity": 1.0,
        }

    similar_product = (
        find_similar_published_product(
            asin=normalized_asin,
            title=title,
        )
    )

    if similar_product:
        return {
            "is_duplicate": True,
            "reason": "similar_published_title",
            "matched_asin": similar_product[
                "asin"
            ],
            "matched_title": similar_product[
                "title"
            ],
            "similarity": similar_product[
                "similarity"
            ],
            "shopify_product_id":
                similar_product[
                    "shopify_product_id"
                ],
            "shopify_handle":
                similar_product[
                    "shopify_handle"
                ],
        }

    return {
        "is_duplicate": False,
        "reason": "",
        "matched_asin": "",
        "matched_title": "",
        "similarity": 0.0,
    }