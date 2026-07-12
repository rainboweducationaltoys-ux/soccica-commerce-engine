import re
from dataclasses import dataclass
from typing import Any

from playwright.sync_api import Page


@dataclass(frozen=True)
class Marketplace:
    code: str
    name: str
    domain: str
    currency: str


MARKETPLACES = [
    Marketplace(
        code="US",
        name="Amazon US",
        domain="www.amazon.com",
        currency="USD",
    ),
    Marketplace(
        code="UK",
        name="Amazon UK",
        domain="www.amazon.co.uk",
        currency="GBP",
    ),
    Marketplace(
        code="DE",
        name="Amazon Germany",
        domain="www.amazon.de",
        currency="EUR",
    ),
]


def normalize_asin(asin: str) -> str:
    cleaned = str(asin).strip().upper()

    if not re.fullmatch(r"[A-Z0-9]{10}", cleaned):
        raise ValueError(f"Geçersiz ASIN: {asin}")

    return cleaned


def build_product_url(
    asin: str,
    marketplace: Marketplace,
) -> str:
    normalized_asin = normalize_asin(asin)

    return (
        f"https://{marketplace.domain}"
        f"/dp/{normalized_asin}"
    )


def get_text(
    page: Page,
    selectors: list[str],
) -> str:
    for selector in selectors:
        try:
            locator = page.locator(selector).first

            if locator.count() == 0:
                continue

            text = locator.inner_text(timeout=5000).strip()

            if text:
                return " ".join(text.split())

        except Exception:
            continue

    return ""


def clean_price_text(price_text: str) -> str:
    if not price_text:
        return ""

    return " ".join(price_text.split())


def extract_price(page: Page) -> str:
    selectors = [
        "#corePrice_feature_div span.a-price span.a-offscreen",
        "#corePriceDisplay_desktop_feature_div span.a-price span.a-offscreen",
        "#price_inside_buybox",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "span.a-price span.a-offscreen",
    ]

    return clean_price_text(
        get_text(page, selectors)
    )


def extract_availability(page: Page) -> str:
    selectors = [
        "#availability",
        "#outOfStock",
        "#deliveryBlockMessage",
        "#mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE",
    ]

    return get_text(page, selectors)


def extract_shipping_to_uae(page: Page) -> str:
    selectors = [
        "#mir-layout-DELIVERY_BLOCK-slot-SECONDARY_DELIVERY_MESSAGE_LARGE",
        "#deliveryBlockMessage",
        "#delivery-message",
        "#exports_desktop_qualifiedBuybox_tlc_feature_div",
        "#amazonGlobal_feature_div",
    ]

    return get_text(page, selectors)


def extract_import_fees(page: Page) -> str:
    selectors = [
        "#importFeesDeposit",
        "#amazonGlobal_feature_div",
        "#exports_desktop_qualifiedBuybox_tlc_feature_div",
        "#deliveryBlockMessage",
    ]

    text = get_text(page, selectors)

    if not text:
        return ""

    import_terms = [
        "import fees",
        "import fee",
        "import charges",
        "estimated import",
        "deposit",
    ]

    lower_text = text.lower()

    if any(term in lower_text for term in import_terms):
        return text

    return ""


def extract_title(page: Page) -> str:
    return get_text(
        page,
        [
            "#productTitle",
            "h1 span",
        ],
    )


def detect_page_status(page: Page) -> str:
    try:
        body_text = page.locator("body").inner_text(
            timeout=5000
        ).lower()
    except Exception:
        return "page_error"

    captcha_terms = [
        "enter the characters you see below",
        "type the characters you see in this image",
        "sorry, we just need to make sure you're not a robot",
    ]

    delivery_block_terms = [
        "cannot be shipped to your selected delivery location",
        "cannot be dispatched to your selected delivery location",
        "cannot be delivered to your selected delivery location",
        "does not ship to your location",
        "choose a different delivery location",
    ]

    unavailable_terms = [
        "currently unavailable",
        "temporarily out of stock",
        "out of stock",
        "derzeit nicht verfügbar",
        "momentan nicht verfügbar",
        "we don't know when or if this item will be back in stock",
    ]

    if any(term in body_text for term in captcha_terms):
        return "captcha"

    if any(term in body_text for term in delivery_block_terms):
        return "not_shippable_to_uae"

    if any(term in body_text for term in unavailable_terms):
        return "unavailable"

    return "ok"


def scrape_marketplace_offer(
    page: Page,
    url: str,
    marketplace_code: str,
    currency: str,
) -> dict[str, Any]:
    print(f"Açılıyor: {marketplace_code} — {url}")

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
    title = extract_title(page)
    price = extract_price(page)
    availability = extract_availability(page)
    shipping_to_uae = extract_shipping_to_uae(page)
    import_fees = extract_import_fees(page)

    if status == "ok" and not title:
        status = "product_not_found"

    elif status == "ok" and not price:
        status = "price_missing"

    return {
        "marketplace": marketplace_code,
        "currency": currency,
        "url": url,
        "status": status,
        "title_found": title,
        "price_text": price,
        "availability": availability,
        "shipping_to_uae": shipping_to_uae,
        "import_fees": import_fees,
    }