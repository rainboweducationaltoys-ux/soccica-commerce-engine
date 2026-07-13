import sys

from metafields_engine import NAMESPACE
from product_store import get_product_by_asin, safe_text
from shopify_api import get_product_with_details


EXPECTED_METAFIELD_KEYS = [
    "asin",
    "source_marketplace",
    "source_url",
    "landed_cost_aed",
    "shopify_price_aed",
    "brand",
    "seo_title",
    "meta_description",
    "product_type",
    "collection_suggestions",
]


def main() -> None:
    if len(sys.argv) != 2:
        print("Kullanım: python verify_publish.py <ASIN>")
        sys.exit(1)

    asin = sys.argv[1].strip().upper()

    product_row = get_product_by_asin(asin)

    if not product_row:
        print(f"ASIN veritabanında bulunamadı: {asin}")
        sys.exit(1)

    shopify_product_id = safe_text(
        product_row.get("shopify_product_id")
    )

    if not shopify_product_id:
        print(
            f"{asin} henüz Shopify'a yayınlanmamış "
            "(shopify_product_id boş)."
        )
        sys.exit(1)

    product = get_product_with_details(
        product_id=shopify_product_id,
        namespace=NAMESPACE,
    )

    if not product:
        print(
            "Shopify'da ürün bulunamadı: "
            f"{shopify_product_id}"
        )
        sys.exit(1)

    print("=" * 70)
    print(f"DOĞRULAMA RAPORU — {asin}")
    print("=" * 70)
    print("Shopify product ID:", product.get("id", ""))
    print("Başlık:", product.get("title", ""))
    print("Handle:", product.get("handle", ""))
    print()

    all_passed = True

    variants = (
        product
        .get("variants", {})
        .get("nodes", [])
    )

    sku = safe_text(
        variants[0].get("sku")
        if variants
        else ""
    )

    sku_pass = sku.upper() == asin

    print("--- SKU KONTROLÜ ---")
    print(f"Beklenen: {asin}")
    print(f"Bulunan:  {sku or '(boş)'}")
    print("Sonuç:", "PASS" if sku_pass else "FAIL")
    print()

    if not sku_pass:
        all_passed = False

    metafield_nodes = (
        product
        .get("metafields", {})
        .get("nodes", [])
    )

    metafield_values = {
        node["key"]: safe_text(node.get("value"))
        for node in metafield_nodes
    }

    print(
        f"--- METAFIELD KONTROLÜ (namespace: {NAMESPACE}) ---"
    )

    for key in EXPECTED_METAFIELD_KEYS:
        value = metafield_values.get(key, "")
        key_pass = bool(value)

        if key_pass:
            print(f"{key}: PASS — değer: {value}")
        else:
            print(f"{key}: FAIL — eksik/boş")
            all_passed = False

    print()
    print("=" * 70)
    print("GENEL SONUÇ:", "PASS" if all_passed else "FAIL")
    print("=" * 70)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
