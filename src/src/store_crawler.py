import re
from urllib.parse import urljoin

from playwright.sync_api import Page


def normalize_product_url(url: str) -> str:
    """
    Amazon ürün linkini sadeleştirir.

    Örnek:
    https://www.amazon.ae/Product/dp/B012345678/ref=...
    ->
    https://www.amazon.ae/dp/B012345678
    """

    match = re.search(
        r"/(?:dp|gp/product)/([A-Z0-9]{10})",
        url,
        re.IGNORECASE,
    )

    if not match:
        return ""

    asin = match.group(1).upper()

    return f"https://www.amazon.ae/dp/{asin}"


def extract_product_links(page: Page) -> list[str]:
    product_links: list[str] = []

    selectors = [
        'a[href*="/dp/"]',
        'a[href*="/gp/product/"]',
        "a.a-link-normal.s-no-outline",
        "h2 a.a-link-normal",
    ]

    for selector in selectors:
        try:
            elements = page.locator(selector)

            for index in range(elements.count()):
                href = elements.nth(index).get_attribute("href")

                if not href:
                    continue

                full_url = urljoin(
                    "https://www.amazon.ae",
                    href,
                )

                normalized_url = normalize_product_url(
                    full_url
                )

                if (
                    normalized_url
                    and normalized_url not in product_links
                ):
                    product_links.append(normalized_url)

        except Exception:
            continue

    return product_links


def find_next_page_url(page: Page) -> str:
    selectors = [
        "a.s-pagination-next",
        "li.a-last a",
    ]

    for selector in selectors:
        try:
            next_button = page.locator(selector).first

            if next_button.count() == 0:
                continue

            classes = next_button.get_attribute("class") or ""

            if "disabled" in classes:
                return ""

            href = next_button.get_attribute("href")

            if href:
                return urljoin(
                    "https://www.amazon.ae",
                    href,
                )

        except Exception:
            continue

    return ""


def crawl_store(
    page: Page,
    store_url: str,
    max_pages: int = 100,
) -> list[str]:
    all_product_links: list[str] = []
    current_url = store_url
    visited_pages: set[str] = set()

    page_number = 1

    while current_url and page_number <= max_pages:
        if current_url in visited_pages:
            print("Aynı sayfa tekrar bulundu. Tarama durduruldu.")
            break

        visited_pages.add(current_url)

        print("\n" + "=" * 60)
        print(f"Mağaza sayfası taranıyor: {page_number}")
        print(current_url)
        print("=" * 60)

        page.goto(
            current_url,
            wait_until="domcontentloaded",
            timeout=90_000,
        )

        try:
            page.wait_for_selector(
                'a[href*="/dp/"]',
                timeout=30_000,
            )
        except Exception:
            print(
                "Bu sayfada ürün bağlantısı bulunamadı "
                "veya sayfa geç yüklendi."
            )

        page_links = extract_product_links(page)

        new_link_count = 0

        for link in page_links:
            if link not in all_product_links:
                all_product_links.append(link)
                new_link_count += 1

        print(
            f"Bu sayfada bulunan yeni ürün: {new_link_count}"
        )
        print(
            f"Toplam bulunan ürün: {len(all_product_links)}"
        )

        next_page_url = find_next_page_url(page)

        if not next_page_url:
            print("Sonraki sayfa bulunamadı. Tarama tamamlandı.")
            break

        current_url = next_page_url
        page_number += 1

    return all_product_links