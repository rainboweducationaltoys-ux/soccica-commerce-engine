import re

SHOPIFY_COLUMNS = [
    "handle",
    "title",
    "body_html",
    "vendor",
    "product_type",
    "tags",
    "published",
    "option1_name",
    "option1_value",
    "variant_sku",
    "variant_price",
    "variant_compare_at_price",
    "variant_requires_shipping",
    "variant_taxable",
    "image_src",
    "image_position",
    "image_alt_text",
]


def create_html_description(
    bullets: list[str],
    description: str,
) -> str:
    parts: list[str] = []

    cleaned_description = description.strip()
    if cleaned_description:
        paragraphs = [
            line.strip()
            for line in cleaned_description.splitlines()
            if line.strip()
        ]

        for paragraph in paragraphs:
            parts.append(f"<p>{paragraph}</p>")

    cleaned_bullets = [
        bullet.strip()
        for bullet in bullets
        if bullet and bullet.strip()
    ]

    if cleaned_bullets:
        bullet_items = "".join(
            f"<li>{bullet}</li>"
            for bullet in cleaned_bullets
        )
        parts.append(f"<ul>{bullet_items}</ul>")

    return "".join(parts)


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "product"


def convert_to_shopify_rows(product: dict) -> list[dict]:
    title = product.get("title", "") or ""
    handle = _slugify(title)
    image_src = product.get("images", [""])[0] if product.get("images") else ""
    price = product.get("price", "") or ""
    description = product.get("description", "") or ""
    brand = product.get("brand", "") or ""

    return [
        {
            "handle": handle,
            "title": title,
            "body_html": description,
            "vendor": brand,
            "product_type": "",
            "tags": "",
            "published": "true",
            "option1_name": "Title",
            "option1_value": "Default Title",
            "variant_sku": product.get("asin", ""),
            "variant_price": price,
            "variant_compare_at_price": price,
            "variant_requires_shipping": "true",
            "variant_taxable": "true",
            "image_src": image_src,
            "image_position": "1",
            "image_alt_text": title,
        }
    ]
