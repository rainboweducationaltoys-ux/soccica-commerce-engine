import time
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

from browser import create_browser, create_context
from scraper import scrape_product
from shopify import convert_to_shopify_rows


BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_FILE = BASE_DIR / "input" / "toys.csv"
OUTPUT_FILE = BASE_DIR / "output" / "toys_enriched_shopify.csv"
ERROR_FILE = BASE_DIR / "output" / "toys_enrichment_errors.csv"


def build_amazon_url(asin: str) -> str:
    return f"https://www.amazon.ae/dp/{asin}"


def main() -> None:
    dataframe = pd.read_csv(INPUT_FILE)

    required_columns = ["Title", "Variant SKU"]

    for column in required_columns:
        if column not in dataframe.columns:
            raise ValueError(
                f"toys.csv içinde '{column}' sütunu bulunamadı."
            )

    all_rows = []
    errors = []

    with sync_playwright() as playwright:
        browser = create_browser(playwright)
        context = create_context(browser)
        page = context.new_page()

        try:
            for index, row in dataframe.iterrows():
                asin = str(row.get("Variant SKU", "")).strip()
                original_title = str(row.get("Title", "")).strip()

                if not asin:
                    continue

                url = build_amazon_url(asin)

                print("=" * 60)
                print(f"Ürün {index + 1}/{len(dataframe)}")
                print("ASIN:", asin)
                print("Başlık:", original_title)

                try:
                    product = scrape_product(page, url)

                    # Mevcut CSV başlığını koru; Amazon başlığı boşsa fallback olur.
                    if original_title:
                        product["title"] = original_title

                    shopify_rows = convert_to_shopify_rows(product)
                    all_rows.extend(shopify_rows)

                    print(
                        f"Başarılı — görsel sayısı: "
                        f"{len(product.get('images', []))}"
                    )

                except Exception as error:
                    print("Hata:", error)

                    errors.append(
                        {
                            "asin": asin,
                            "title": original_title,
                            "url": url,
                            "error": str(error),
                        }
                    )

                time.sleep(3)

        finally:
            context.close()
            browser.close()

    pd.DataFrame(all_rows).to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    pd.DataFrame(errors).to_csv(
        ERROR_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("\nTamamlandı.")
    print("Shopify CSV:", OUTPUT_FILE)
    print("Hata dosyası:", ERROR_FILE)


if __name__ == "__main__":
    main()