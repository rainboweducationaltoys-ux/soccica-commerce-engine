import json
from typing import Any


NAMESPACE = "soccica"


def safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def build_product_metafields(
    product_id: str,
    asin: str,
    marketplace: str,
    source_url: str,
    landed_cost_aed: float,
    shopify_price_aed: float,
    brand: str,
    seo_title: str,
    meta_description: str,
    product_type: str,
    collections: list[str] | None = None,
) -> list[dict[str, str]]:
    metafields: list[dict[str, str]] = []

    def add(
        key: str,
        value: Any,
        metafield_type: str = "single_line_text_field",
    ) -> None:
        text = safe_text(value)

        if not text:
            return

        metafields.append(
            {
                "ownerId": product_id,
                "namespace": NAMESPACE,
                "key": key,
                "type": metafield_type,
                "value": text,
            }
        )

    add("asin", asin)
    add("source_marketplace", marketplace)
    add("source_url", source_url, "url")
    add(
        "landed_cost_aed",
        round(float(landed_cost_aed), 2),
        "number_decimal",
    )
    add(
        "shopify_price_aed",
        round(float(shopify_price_aed), 2),
        "number_decimal",
    )
    add("brand", brand)
    add("seo_title", seo_title)
    add(
        "meta_description",
        meta_description,
        "multi_line_text_field",
    )
    add("product_type", product_type)

    if collections:
        add(
            "collection_suggestions",
            json.dumps(
                collections,
                ensure_ascii=False,
            ),
            "json",
        )

    return metafields