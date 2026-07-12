import re
from typing import Any

from playwright.sync_api import Page

from marketplace_scraper import (
    Marketplace,
    build_product_url,
    detect_page_status,
    extract_availability,
    extract_import_fees,
    extract_price,
    extract_shipping_to_uae,
)
from utils import (
    get_brand,
    get_bullets,
    get_description,
    get_images,
    get_title,
)


def extract_aed_amount(value: Any) -> float:
    if value is None:
        return 0.0

    text = str(value).strip()

    if not text:
        return 0.0

    match = re.search(
        r"AED\s*([\d,]+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )

    if not match:
        return 0.0

    return float(
        match.group(1).replace(",", "")
    )


def calculate_extra_charges(
    shipping_text: str,
    import_text: str,
) -> tuple[float, str]:
    import_amount = extract_aed_amount(import_text)
    shipping_amount = extract_aed_amount(shipping_text)

    # Amazon bazen kargo + ithalat ücretini tek toplam olarak gösterir.
    if import_amount > 0:
        return (
            import_amount,
            "combined_shipping_import",
        )

    if shipping_amount > 0:
        return (
            shipping_amount,
            "shipping_only",
        )

    return (0.0, "charges_missing")


def scrape_complete_offer(
    page: Page,
    asin: str,
    marketplace: Marketplace,
) -> dict[str, Any]:
    url = build_product_url(
        asin=asin,
        marketplace=marketplace,
    )

    print(
        f"{asin} — {marketplace.code} açılıyor:"
    )
    print(url)

    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=90_000,
    )

    try:
        page.locator("#productTitle").wait_for(
            state="visible",
            timeout=20_000,
        )
    except Exception:
        pass

    status = detect_page_status(page)

    title = get_title(page)
    price_text = extract_price(page)
    availability = extract_availability(page)
    shipping_text = extract_shipping_to_uae(page)
    import_text = extract_import_fees(page)

    if status == "ok" and not title:
        status = "product_not_found"

    if status == "ok" and not price_text:
        status = "price_missing"

    item_price_aed = extract_aed_amount(
        price_text
    )

    extra_charges_aed, charges_type = (
        calculate_extra_charges(
            shipping_text=shipping_text,
            import_text=import_text,
        )
    )

    landed_cost_aed = round(
        item_price_aed + extra_charges_aed,
        2,
    )

    result: dict[str, Any] = {
        "asin": asin,
        "marketplace": marketplace.code,
        "marketplace_name": marketplace.name,
        "currency": marketplace.currency,
        "source_url": url,
        "status": status,
        "title": title,
        "price_text": price_text,
        "availability": availability,
        "shipping_to_uae": shipping_text,
        "import_fees": import_text,
        "item_price_aed": item_price_aed,
        "extra_charges_aed": extra_charges_aed,
        "charges_type": charges_type,
        "landed_cost_aed": landed_cost_aed,
        "eligible": False,
        "brand": "",
        "bullets": [],
        "description": "",
        "images": [],
    }

    # Geçerli teklif olabilmesi için fiyat ve ek ücretler bilinmeli.
    if (
        status == "ok"
        and item_price_aed > 0
        and extra_charges_aed > 0
    ):
        result["eligible"] = True

        # Aynı sayfa açıkken Shopify için gereken verileri de al.
        result["brand"] = get_brand(page)
        result["bullets"] = get_bullets(page)
        result["description"] = get_description(page)
        result["images"] = get_images(page)

    return result