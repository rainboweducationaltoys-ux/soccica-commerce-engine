import re

from playwright.sync_api import Page

from config import PAGE_TIMEOUT
from utils import (
    get_asin,
    get_bullets,
    get_brand,
    get_description,
    get_images,
    get_price,
    get_text,
    get_title,
)


def scrape_product(page: Page, url: str) -> dict:
    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=PAGE_TIMEOUT,
    )

    try:
        page.wait_for_load_state(
            "load",
            timeout=min(10_000, PAGE_TIMEOUT),
        )
    except Exception:
        pass

    for _ in range(3):
        title = get_title(page)
        if title:
            break
        page.wait_for_timeout(1000)

    title = get_title(page)

    if not title:
        raise ValueError("Ürün başlığı bulunamadı.")

    price = get_price(page)
    brand = get_brand(page)
    bullets = get_bullets(page)
    description = get_description(page)
    images = get_images(page)
    asin = get_asin(url)

    rating = extract_rating(page)
    review_count = extract_review_count(page)
    availability = extract_availability(page)
    category = extract_category(page)
    technical_details = extract_technical_details(page)
    variations = extract_variations(page)

    manufacturer = get_detail_value(
        technical_details,
        ["manufacturer"],
    )
    model_number = get_detail_value(
        technical_details,
        ["item model number", "model number", "model name"],
    )
    product_dimensions = get_detail_value(
        technical_details,
        ["product dimensions", "package dimensions"],
    )
    item_weight = get_detail_value(
        technical_details,
        ["item weight", "product weight"],
    )
    country_of_origin = get_detail_value(
        technical_details,
        ["country of origin"],
    )

    print("Başlık:", title)
    print("Fiyat:", price)
    print("ASIN:", asin)
    print("Görsel sayısı:", len(images))
    print("Rating:", rating)
    print("Yorum sayısı:", review_count)
    print("Stok:", availability)
    print("Kategori:", category)
    print("Varyasyonlar:", variations)

    return {
        "asin": asin,
        "url": url,
        "title": title,
        "price": price,
        "brand": brand,
        "bullets": bullets,
        "description": description,
        "images": images,
        "rating": rating,
        "review_count": review_count,
        "availability": availability,
        "category": category,
        "manufacturer": manufacturer,
        "model_number": model_number,
        "product_dimensions": product_dimensions,
        "item_weight": item_weight,
        "country_of_origin": country_of_origin,
        "technical_details": technical_details,
        "variations": variations,
    }


def extract_rating(page: Page) -> str:
    selectors = [
        "#acrPopover",
        "span[data-hook='rating-out-of-text']",
        "i[data-hook='average-star-rating'] span",
    ]

    for selector in selectors:
        try:
            element = page.locator(selector).first

            if element.count() == 0:
                continue

            text = (
                element.get_attribute("title")
                or element.inner_text(timeout=5000)
            )

            if text:
                match = re.search(r"\d+(?:[.,]\d+)?", text)

                if match:
                    return match.group(0).replace(",", ".")

        except Exception:
            continue

    return ""


def extract_review_count(page: Page) -> str:
    selectors = [
        "#acrCustomerReviewText",
        "span[data-hook='total-review-count']",
    ]

    for selector in selectors:
        text = get_text(page, selector)

        if text:
            digits = re.sub(r"[^\d]", "", text)

            if digits:
                return digits

    return ""


def extract_availability(page: Page) -> str:
    selectors = [
        "#availability",
        "#outOfStock",
        "#deliveryBlockMessage",
    ]

    for selector in selectors:
        text = get_text(page, selector)

        if text:
            return " ".join(text.split())

    return ""


def extract_category(page: Page) -> str:
    categories: list[str] = []

    selectors = [
        "#wayfinding-breadcrumbs_feature_div ul li a",
        "#wayfinding-breadcrumbs_container ul li a",
    ]

    for selector in selectors:
        try:
            elements = page.locator(selector)

            for index in range(elements.count()):
                text = elements.nth(index).inner_text().strip()

                if text and text not in categories:
                    categories.append(text)

        except Exception:
            continue

        if categories:
            break

    return " > ".join(categories)


def extract_technical_details(page: Page) -> dict[str, str]:
    details: dict[str, str] = {}

    table_selectors = [
        "#productDetails_techSpec_section_1 tr",
        "#productDetails_techSpec_section_2 tr",
        "#productDetails_detailBullets_sections1 tr",
        "#technicalSpecifications_section_1 tr",
    ]

    for selector in table_selectors:
        try:
            rows = page.locator(selector)

            for index in range(rows.count()):
                row = rows.nth(index)

                key_locator = row.locator("th").first
                value_locator = row.locator("td").first

                if (
                    key_locator.count() == 0
                    or value_locator.count() == 0
                ):
                    continue

                key = key_locator.inner_text().strip()
                value = value_locator.inner_text().strip()

                key = " ".join(key.split())
                value = " ".join(value.split())

                if key and value:
                    details[key] = value

        except Exception:
            continue

    try:
        bullet_rows = page.locator(
            "#detailBullets_feature_div li"
        )

        for index in range(bullet_rows.count()):
            text = bullet_rows.nth(index).inner_text().strip()

            if ":" not in text:
                continue

            key, value = text.split(":", 1)

            key = " ".join(key.split())
            value = " ".join(value.split())

            if key and value:
                details[key] = value

    except Exception:
        pass

    return details


def get_detail_value(
    details: dict[str, str],
    possible_keys: list[str],
) -> str:
    for detail_key, detail_value in details.items():
        normalized_key = detail_key.lower()

        for possible_key in possible_keys:
            if possible_key.lower() in normalized_key:
                return detail_value

    return ""


def extract_variations(page: Page) -> dict[str, list[dict[str, str]]]:
    variations: dict[str, list[dict[str, str]]] = {}

    dimension_selectors = [
        "#variation_color_name",
        "#variation_size_name",
        "#variation_style_name",
        "#variation_pattern_name",
        "#variation_number_of_items",
    ]

    for selector in dimension_selectors:
        try:
            container = page.locator(selector).first

            if container.count() == 0:
                continue

            label = ""

            try:
                label = container.locator("label").first.inner_text().strip()
            except Exception:
                pass

            if ":" in label:
                label = label.split(":", 1)[0].strip()

            if not label:
                label = (
                    selector
                    .replace("#variation_", "")
                    .replace("_", " ")
                    .title()
                )

            options: list[dict[str, str]] = []

            option_elements = container.locator(
                "li, option, span.a-button-text"
            )

            for index in range(option_elements.count()):
                element = option_elements.nth(index)

                text = element.inner_text().strip()

                if not text:
                    continue

                asin = (
                    element.get_attribute("data-defaultasin")
                    or element.get_attribute("data-asin")
                    or ""
                )

                option = {
                    "value": " ".join(text.split()),
                    "asin": asin,
                }

                if option not in options:
                    options.append(option)

            if options:
                variations[label] = options

        except Exception:
            continue

    return variations