import json
import random
import time
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

from browser import create_browser, create_context
from config import (
    AMAZON_OUTPUT_FILE,
    ERROR_OUTPUT_FILE,
    MAX_RETRIES,
    OUTPUT_DIR,
    PRODUCTS_FILE,
    PROGRESS_FILE,
    SHOPIFY_OUTPUT_FILE,
    WAIT_BETWEEN_PRODUCTS_MAX,
    WAIT_BETWEEN_PRODUCTS_MIN,
)
from image_downloader import download_product_images
from scraper import scrape_product
from shopify import SHOPIFY_COLUMNS, convert_to_shopify_rows


def scrape_with_retry(
    page,
    url: str,
    max_retries: int = MAX_RETRIES,
):
    last_error = None

    for attempt in range(1, max_retries + 1):
        print(f"Deneme {attempt}/{max_retries}")

        try:
            return scrape_product(page, url)

        except Exception as error:
            import traceback

            last_error = error

            print("\n================ ERROR ================\n")
            traceback.print_exc()
            print("\n=======================================\n")

            if attempt < max_retries:
                wait_seconds = random.uniform(2, 5)

                print(
                    f"Tekrar deneme öncesi "
                    f"{wait_seconds:.1f} saniye bekleniyor..."
                )

                time.sleep(wait_seconds)

    if last_error is not None:
        raise last_error

    raise RuntimeError("Ürün çekme denemeleri bitti.")

def save_shopify_product(product: dict) -> None:
    rows = convert_to_shopify_rows(product)

    for row in rows:
        append_row_to_csv(row, SHOPIFY_OUTPUT_FILE, SHOPIFY_COLUMNS)


def save_error(url: str, error_message: str) -> None:
    append_row_to_csv(
        {"url": url, "error": error_message},
        ERROR_OUTPUT_FILE,
        ["url", "error"],
    )


def ensure_directories() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_product_urls() -> list[str]:
    if not PRODUCTS_FILE.exists():
        raise FileNotFoundError(
            f"Girdi dosyası bulunamadı: {PRODUCTS_FILE}"
        )

    dataframe = pd.read_csv(PRODUCTS_FILE)

    if "url" not in dataframe.columns:
        raise ValueError(
            "products.csv dosyasında 'url' isimli sütun bulunmalıdır."
        )

    urls: list[str] = []

    for value in dataframe["url"].dropna():
        url = str(value).strip()

        if url and url not in urls:
            urls.append(url)

    return urls


def load_completed_urls() -> set[str]:
    if not PROGRESS_FILE.exists():
        return set()

    try:
        progress_dataframe = pd.read_csv(PROGRESS_FILE)

        if "url" not in progress_dataframe.columns:
            return set()

        return set(
            progress_dataframe["url"]
            .dropna()
            .astype(str)
            .str.strip()
        )

    except Exception:
        return set()


def save_progress(url: str, asin: str, status: str) -> None:
    new_row = pd.DataFrame(
        [
            {
                "url": url,
                "asin": asin,
                "status": status,
            }
        ]
    )

    file_exists = PROGRESS_FILE.exists()

    new_row.to_csv(
        PROGRESS_FILE,
        mode="a",
        header=not file_exists,
        index=False,
        encoding="utf-8-sig",
    )


def append_row_to_csv(
    row: dict,
    output_file: Path,
    columns: list[str] | None = None,
) -> None:
    dataframe = pd.DataFrame([row])

    if columns:
        dataframe = dataframe.reindex(columns=columns)

    file_exists = output_file.exists()

    dataframe.to_csv(
        output_file,
        mode="a",
        header=not file_exists,
        index=False,
        encoding="utf-8-sig",
    )


def get_image_list(product: dict) -> list[str]:
    images = product.get("images", []) or []

    if isinstance(images, str):
        return [images] if images.strip() else []

    if isinstance(images, (list, tuple, set)):
        return [str(image).strip() for image in images if str(image).strip()]

    return []


def get_downloaded_image_list(product: dict) -> list[str]:
    downloaded_images = product.get("downloaded_images", []) or []

    if isinstance(downloaded_images, str):
        return [downloaded_images] if downloaded_images.strip() else []

    if isinstance(downloaded_images, (list, tuple, set)):
        return [str(image).strip() for image in downloaded_images if str(image).strip()]

    return []


def save_raw_product(product: dict) -> None:
    raw_row = {
        "asin": product.get("asin", ""),
        "url": product.get("url", ""),
        "title": product.get("title", ""),
        "price": product.get("price", ""),
        "brand": product.get("brand", ""),

        "bullet_1": (
            product.get("bullets", [])[0]
            if len(product.get("bullets", [])) > 0
            else ""
        ),
        "bullet_2": (
            product.get("bullets", [])[1]
            if len(product.get("bullets", [])) > 1
            else ""
        ),
        "bullet_3": (
            product.get("bullets", [])[2]
            if len(product.get("bullets", [])) > 2
            else ""
        ),
        "bullet_4": (
            product.get("bullets", [])[3]
            if len(product.get("bullets", [])) > 3
            else ""
        ),
        "bullet_5": (
            product.get("bullets", [])[4]
            if len(product.get("bullets", [])) > 4
            else ""
        ),

        "description": product.get("description", ""),
        "images": " | ".join(product.get("images", [])),
        "downloaded_images": " | ".join(
            str(path)
            for path in product.get("downloaded_images", [])
        ),

        "rating": product.get("rating", ""),
        "review_count": product.get("review_count", ""),
        "availability": product.get("availability", ""),
        "category": product.get("category", ""),
        "manufacturer": product.get("manufacturer", ""),
        "model_number": product.get("model_number", ""),
        "product_dimensions": product.get(
            "product_dimensions",
            "",
        ),
        "item_weight": product.get("item_weight", ""),
        "country_of_origin": product.get(
            "country_of_origin",
            "",
        ),
        "technical_details": json.dumps(
            product.get("technical_details", {}),
            ensure_ascii=False,
        ),
        "variations": json.dumps(
    product.get("variations", {}),
    ensure_ascii=False,
),
    }

    append_row_to_csv(
        raw_row,
        AMAZON_OUTPUT_FILE,
    )


def main() -> None:
    ensure_directories()

    urls = load_product_urls()
    completed_urls = load_completed_urls()

    pending_urls = [
        url
        for url in urls
        if url not in completed_urls
    ]

    print("=" * 60)
    print("Soccica Amazon Importer")
    print("=" * 60)
    print(f"Toplam URL: {len(urls)}")
    print(f"Daha önce tamamlanan: {len(completed_urls)}")
    print(f"İşlenecek URL: {len(pending_urls)}")

    if not pending_urls:
        print("\nİşlenecek yeni ürün bulunamadı.")
        return

    successful_count = 0
    failed_count = 0

    with sync_playwright() as playwright:
        browser = create_browser(playwright)
        context = create_context(browser)
        page = context.new_page()

        try:
            for index, url in enumerate(
                pending_urls,
                start=1,
            ):
                print("\n" + "=" * 60)
                print(
                    f"Ürün {index}/{len(pending_urls)}"
                )
                print("=" * 60)

                try:
                    product = scrape_with_retry(
                        page,
                        url,
                    )
                    downloaded_images = download_product_images(product)
                    product["downloaded_images"] = downloaded_images

                    save_raw_product(product)
                    save_shopify_product(product)

                    save_progress(
                        url=url,
                        asin=product.get("asin", ""),
                        status="success",
                    )

                    successful_count += 1

                    print("Ürün başarıyla kaydedildi.")

                except Exception as error:
                    error_message = str(error)
                    print(error)

                    print(
                        f"Ürün çekilemedi: {error_message}"
                    )

                    save_error(
                        url,
                        error_message,
                    )

                    save_progress(
                        url=url,
                        asin="",
                        status="failed",
                    )

                    failed_count += 1

                if index < len(pending_urls):
                    wait_seconds = random.uniform(
                        WAIT_BETWEEN_PRODUCTS_MIN,
                        WAIT_BETWEEN_PRODUCTS_MAX,
                    )

                    print(
                        f"{wait_seconds:.1f} saniye bekleniyor..."
                    )

                    time.sleep(wait_seconds)

        finally:
            context.close()
            browser.close()

    print("\n" + "=" * 60)
    print("İşlem tamamlandı")
    print("=" * 60)
    print(f"Başarılı ürün: {successful_count}")
    print(f"Hatalı ürün: {failed_count}")
    print(f"Amazon çıktısı: {AMAZON_OUTPUT_FILE}")
    print(f"Shopify çıktısı: {SHOPIFY_OUTPUT_FILE}")
    print(f"Hata dosyası: {ERROR_OUTPUT_FILE}")
    print(f"İlerleme dosyası: {PROGRESS_FILE}")


if __name__ == "__main__":
    main()