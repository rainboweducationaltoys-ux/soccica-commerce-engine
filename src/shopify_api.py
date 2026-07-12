import os
import time
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv()


SHOPIFY_SHOP = os.getenv("SHOPIFY_SHOP", "").strip()
SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID", "").strip()
SHOPIFY_CLIENT_SECRET = os.getenv(
    "SHOPIFY_CLIENT_SECRET",
    "",
).strip()
SHOPIFY_API_VERSION = os.getenv(
    "SHOPIFY_API_VERSION",
    "2026-07",
).strip()

_cached_token: str | None = None
_token_expires_at: float = 0


def normalize_shop_domain(shop: str) -> str:
    cleaned = shop.strip()
    cleaned = cleaned.removeprefix("https://")
    cleaned = cleaned.removeprefix("http://")
    cleaned = cleaned.rstrip("/")

    if cleaned.endswith(".myshopify.com"):
        return cleaned

    return f"{cleaned}.myshopify.com"


def validate_settings() -> None:
    missing: list[str] = []

    if not SHOPIFY_SHOP:
        missing.append("SHOPIFY_SHOP")

    if not SHOPIFY_CLIENT_ID:
        missing.append("SHOPIFY_CLIENT_ID")

    if not SHOPIFY_CLIENT_SECRET:
        missing.append("SHOPIFY_CLIENT_SECRET")

    if missing:
        raise ValueError(
            "Eksik Shopify ayarları: "
            + ", ".join(missing)
        )


def get_shop_domain() -> str:
    validate_settings()
    return normalize_shop_domain(SHOPIFY_SHOP)


def get_access_token() -> str:
    global _cached_token
    global _token_expires_at

    validate_settings()

    if (
        _cached_token
        and time.time() < _token_expires_at - 60
    ):
        return _cached_token

    shop_domain = get_shop_domain()

    token_url = (
        f"https://{shop_domain}"
        "/admin/oauth/access_token"
    )

    response = requests.post(
        token_url,
        headers={
            "Content-Type":
                "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "client_credentials",
            "client_id": SHOPIFY_CLIENT_ID,
            "client_secret": SHOPIFY_CLIENT_SECRET,
        },
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            "Shopify token alınamadı: "
            f"{response.status_code} - {response.text}"
        )

    payload = response.json()

    access_token = payload.get("access_token")
    expires_in = int(
        payload.get("expires_in", 86399)
    )

    if not access_token:
        raise RuntimeError(
            f"Shopify access token dönmedi: {payload}"
        )

    _cached_token = access_token
    _token_expires_at = time.time() + expires_in

    return access_token


def graphql_request(
    query: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    access_token = get_access_token()
    shop_domain = get_shop_domain()

    endpoint = (
        f"https://{shop_domain}"
        f"/admin/api/{SHOPIFY_API_VERSION}"
        "/graphql.json"
    )

    response = requests.post(
        endpoint,
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": access_token,
        },
        json={
            "query": query,
            "variables": variables or {},
        },
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            "Shopify GraphQL HTTP hatası: "
            f"{response.status_code} - {response.text}"
        )

    payload = response.json()

    if payload.get("errors"):
        raise RuntimeError(
            f"Shopify GraphQL hatası: {payload['errors']}"
        )

    return payload


def test_connection() -> dict[str, str]:
    query = """
    query ShopInfo {
      shop {
        name
        myshopifyDomain
      }
    }
    """

    payload = graphql_request(query)
    shop = payload["data"]["shop"]

    return {
        "name": shop["name"],
        "domain": shop["myshopifyDomain"],
    }


def build_media(
    image_urls: list[str],
) -> list[dict[str, str]]:
    media: list[dict[str, str]] = []
    seen: set[str] = set()

    for position, image_url in enumerate(
        image_urls,
        start=1,
    ):
        image_url = str(image_url).strip()

        if (
            not image_url
            or not image_url.startswith("http")
            or image_url in seen
        ):
            continue

        seen.add(image_url)

        media.append(
            {
                "mediaContentType": "IMAGE",
                "originalSource": image_url,
                "alt": f"Product image {position}",
            }
        )

    return media


def get_user_error_messages(
    user_errors: list[dict[str, Any]],
) -> list[str]:
    messages: list[str] = []

    for error in user_errors:
        field = error.get("field")
        message = error.get(
            "message",
            "Bilinmeyen hata",
        )

        if field:
            messages.append(
                f"{field}: {message}"
            )
        else:
            messages.append(message)

    return messages


def create_draft_product(
    title: str,
    description_html: str,
    vendor: str,
    product_type: str,
    tags: list[str],
    image_urls: list[str],
) -> dict[str, Any]:
    mutation = """
    mutation CreateProduct(
      $product: ProductCreateInput!
      $media: [CreateMediaInput!]
    ) {
      productCreate(
        product: $product
        media: $media
      ) {
        product {
          id
          title
          handle
          status
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "product": {
            "title": title,
            "descriptionHtml": description_html,
            "vendor": vendor,
            "productType": product_type,
            "tags": tags,
            "status": "DRAFT",
        },
        "media": build_media(image_urls),
    }

    payload = graphql_request(
        query=mutation,
        variables=variables,
    )

    result = payload["data"]["productCreate"]
    user_errors = result.get("userErrors", [])

    if user_errors:
        messages = get_user_error_messages(
            user_errors
        )
        raise RuntimeError(
            "Shopify ürün oluşturma hatası: "
            + " | ".join(messages)
        )

    product = result.get("product")

    if not product:
        raise RuntimeError(
            "Shopify ürün bilgisi dönmedi."
        )

    return product


def update_default_variant(
    product_id: str,
    variant_id: str,
    price: float,
    sku: str,
) -> dict[str, Any]:
    mutation = """
    mutation UpdateDefaultVariant(
      $productId: ID!
      $variants: [ProductVariantsBulkInput!]!
    ) {
      productVariantsBulkUpdate(
        productId: $productId
        variants: $variants
      ) {
        productVariants {
          id
          price
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "productId": product_id,
        "variants": [
            {
                "id": variant_id,
                "price": str(round(float(price), 2)),
            }
        ],
    }

    payload = graphql_request(
        query=mutation,
        variables=variables,
    )

    result = payload["data"]["productVariantsBulkUpdate"]
    user_errors = result.get("userErrors", [])

    if user_errors:
        messages = get_user_error_messages(
            user_errors
        )
        raise RuntimeError(
            "Shopify varyant güncelleme hatası: "
            + " | ".join(messages)
        )

    variants = result.get("productVariants", [])

    if not variants:
        raise RuntimeError(
            "Shopify varyant bilgisi dönmedi."
        )

    variant = variants[0]
    variant["sku"] = sku

    return variant


def update_inventory_item_sku(
    inventory_item_id: str,
    sku: str,
) -> dict[str, Any]:
    mutation = """
    mutation UpdateInventoryItem(
      $id: ID!
      $input: InventoryItemInput!
    ) {
      inventoryItemUpdate(
        id: $id
        input: $input
      ) {
        inventoryItem {
          id
          sku
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "id": inventory_item_id,
        "input": {
            "sku": sku,
        },
    }

    payload = graphql_request(
        query=mutation,
        variables=variables,
    )

    result = payload["data"]["inventoryItemUpdate"]
    user_errors = result.get("userErrors", [])

    if user_errors:
        messages = get_user_error_messages(
            user_errors
        )
        raise RuntimeError(
            "Shopify SKU güncelleme hatası: "
            + " | ".join(messages)
        )

    inventory_item = result.get("inventoryItem")

    if not inventory_item:
        raise RuntimeError(
            "Shopify inventory item bilgisi dönmedi."
        )

    return inventory_item


def create_draft_product_with_price(
    title: str,
    description_html: str,
    vendor: str,
    product_type: str,
    tags: list[str],
    image_urls: list[str],
    price: float,
    sku: str,
) -> dict[str, Any]:
    mutation = """
    mutation CreateProduct(
      $product: ProductCreateInput!
      $media: [CreateMediaInput!]
    ) {
      productCreate(
        product: $product
        media: $media
      ) {
        product {
          id
          title
          handle
          status
          variants(first: 1) {
            nodes {
              id
              inventoryItem {
                id
              }
            }
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "product": {
            "title": title,
            "descriptionHtml": description_html,
            "vendor": vendor,
            "productType": product_type,
            "tags": tags,
            "status": "DRAFT",
        },
        "media": build_media(image_urls),
    }

    payload = graphql_request(
        query=mutation,
        variables=variables,
    )

    result = payload["data"]["productCreate"]
    user_errors = result.get("userErrors", [])

    if user_errors:
        messages = get_user_error_messages(
            user_errors
        )
        raise RuntimeError(
            "Shopify ürün oluşturma hatası: "
            + " | ".join(messages)
        )

    product = result.get("product")

    if not product:
        raise RuntimeError(
            "Shopify ürün bilgisi dönmedi."
        )

    variant_nodes = (
        product
        .get("variants", {})
        .get("nodes", [])
    )

    if not variant_nodes:
        raise RuntimeError(
            "Varsayılan Shopify varyantı bulunamadı."
        )

    variant_node = variant_nodes[0]

    variant = update_default_variant(
        product_id=product["id"],
        variant_id=variant_node["id"],
        price=price,
        sku=sku,
    )

    inventory_item_id = (
        variant_node
        .get("inventoryItem", {})
        .get("id", "")
    )

    if not inventory_item_id:
        raise RuntimeError(
            "Shopify inventory item ID bulunamadı."
        )

    inventory_item = update_inventory_item_sku(
        inventory_item_id=inventory_item_id,
        sku=sku,
    )

    variant["sku"] = inventory_item.get(
        "sku",
        sku,
    )
    variant["inventory_item_id"] = (
        inventory_item.get("id", "")
    )

    product["variant"] = variant

    return product


def find_product_by_asin(
    asin: str,
) -> dict[str, Any] | None:
    asin = str(asin).strip().upper()

    if not asin:
        return None

    query = """
    query FindProductByAsin($query: String!) {
      products(first: 1, query: $query) {
        nodes {
          id
          title
          handle
          status
          tags
        }
      }
    }
    """

    payload = graphql_request(
        query=query,
        variables={
            "query": f"tag:'ASIN:{asin}'",
        },
    )

    products = (
        payload
        .get("data", {})
        .get("products", {})
        .get("nodes", [])
    )

    if not products:
        return None

    return products[0]
def set_product_metafields(
    metafields: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if not metafields:
        return []

    mutation = """
    mutation SetProductMetafields(
      $metafields: [MetafieldsSetInput!]!
    ) {
      metafieldsSet(
        metafields: $metafields
      ) {
        metafields {
          id
          namespace
          key
          type
          value
        }
        userErrors {
          field
          message
          code
        }
      }
    }
    """

    payload = graphql_request(
        query=mutation,
        variables={
            "metafields": metafields,
        },
    )

    result = payload["data"]["metafieldsSet"]

    user_errors = result.get(
        "userErrors",
        [],
    )

    if user_errors:
        messages = get_user_error_messages(
            user_errors
        )

        raise RuntimeError(
            "Shopify metafield hatası: "
            + " | ".join(messages)
        )

    return result.get(
        "metafields",
        [],
    )