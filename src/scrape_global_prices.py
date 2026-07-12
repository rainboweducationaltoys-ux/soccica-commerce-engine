import time
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

from browser import create_browser, create_context
from marketplace_scraper import scrape_marketplace_offer


BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_FILE = (
    BASE_DIR
    / "output"
    / "global_prices"
    / "marketplace_urls.csv"
)

OUTPUT_FILE = (
    BASE_DIR
    / "output"
    / "global_prices"
    / "marketplace_prices.csv"
)


def main() -> None:
    dataframe = pd.read_csv(INPUT_FILE)

    results = []

    with sync_playwright() as playwright:
        browser = create_browser(playwright)
        context = create_context(browser)
        page = context.new_page()

        try:
            for index, row in dataframe.iterrows():
                print("=" * 60)
                print(
                    f"Sayfa {index + 1}/{len(dataframe)}"
                )

                asin = str(row["asin"]).strip()
                original_title = str(
                    row.get("title", "")
                ).strip()

                try:
                    offer = scrape_marketplace_offer(
                        page=page,
                        url=str(row["product_url"]),
                        marketplace_code=str(
                            row["marketplace"]
                        ),
                        currency=str(row["currency"]),
                    )

                    offer["asin"] = asin
                    offer["original_title"] = (
                        original_title
                    )

                    results.append(offer)

                    print(
                        "Fiyat:",
                        offer["price_text"],
                    )
                    print(
                        "Stok:",
                        offer["availability"],
                    )
                    print(
                        "Durum:",
                        offer["status"],
                    )

                except Exception as error:
                    results.append(
                        {
                            "asin": asin,
                            "original_title": original_title,
                            "marketplace": row[
                                "marketplace"
                            ],
                            "currency": row["currency"],
                            "url": row["product_url"],
                            "status": "error",
                            "title_found": "",
                            "price_text": "",
                            "availability": "",
                            "error": str(error),
                        }
                    )

                    print("Hata:", error)

                time.sleep(2)

        finally:
            context.close()
            browser.close()

    result_df = pd.DataFrame(results)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("\nTamamlandı.")
    print("Dosya:", OUTPUT_FILE)


if __name__ == "__main__":
    main()