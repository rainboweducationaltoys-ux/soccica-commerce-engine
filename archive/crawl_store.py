import pandas as pd
from playwright.sync_api import sync_playwright

from browser import create_browser, create_context
from src.store_crawler import crawl_store


STORE_FILE = "input/store.csv"
PRODUCTS_FILE = "input/products.csv"


def load_store_url() -> str:
    dataframe = pd.read_csv(STORE_FILE)

    if "store_url" not in dataframe.columns:
        raise ValueError(
            "store.csv içinde 'store_url' sütunu bulunmalıdır."
        )

    values = dataframe["store_url"].dropna()

    if values.empty:
        raise ValueError(
            "store.csv içinde mağaza linki bulunamadı."
        )

    return str(values.iloc[0]).strip()


def save_product_links(product_links: list[str]) -> None:
    dataframe = pd.DataFrame(
        {
            "url": product_links,
        }
    )

    dataframe.to_csv(
        PRODUCTS_FILE,
        index=False,
        encoding="utf-8-sig",
    )


def main() -> None:
    store_url = load_store_url()

    print("=" * 60)
    print("Soccica Store Crawler")
    print("=" * 60)
    print("Mağaza linki:")
    print(store_url)

    with sync_playwright() as playwright:
        browser = create_browser(playwright)
        context = create_context(browser)
        page = context.new_page()

        try:
            product_links = crawl_store(
                page=page,
                store_url=store_url,
                max_pages=100,
            )
        finally:
            context.close()
            browser.close()

    save_product_links(product_links)

    print("\n" + "=" * 60)
    print("Mağaza taraması tamamlandı")
    print("=" * 60)
    print(f"Bulunan toplam ürün: {len(product_links)}")
    print(f"Dosya oluşturuldu: {PRODUCTS_FILE}")


if __name__ == "__main__":
    main()