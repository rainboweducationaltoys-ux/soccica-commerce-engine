import os
from typing import Any

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from browser import create_browser, create_context
from database import (
    get_spotlight_priced_asins,
    get_status_summary,
    initialize_database,
    recover_processing_products,
    update_product_status,
)
from logging_setup import configure_logging
from pricing_engine import calculate_spotlight_selling_price
from product_engine import scrape_content_only
from product_store import (
    get_product_by_asin,
    migrate_product_table,
    save_scraped_product,
)
from spotlight_importer import import_spotlight_export


load_dotenv()

logger = configure_logging("soccica.spotlight_pipeline")


SPOTLIGHT_BATCH_SIZE = int(
    os.getenv("SPOTLIGHT_BATCH_SIZE", "100")
)


def print_status_summary() -> None:
    summary = get_status_summary()

    logger.info("DB durumu: %s", summary)

    print("\n" + "-" * 70)
    print("VERİTABANI DURUMU")
    print("-" * 70)
    print("Toplam:", summary.get("total", 0))
    print("Bekleyen:", summary.get("pending", 0))
    print(
        "Spotlight fiyatlandı:",
        summary.get("spotlight_priced", 0),
    )
    print(
        "Shopify için hazır:",
        summary.get("ready_for_shopify", 0),
    )
    print("Yayınlanan:", summary.get("published", 0))
    print("Hatalı:", summary.get("error", 0))
    print("-" * 70)


def process_spotlight_asin(
    page,
    asin: str,
) -> bool:
    db_product = get_product_by_asin(asin)

    if not db_product:
        logger.error(
            "%s: veritabanında bulunamadı, atlanıyor.",
            asin,
        )

        return False

    source_url = db_product.get("source_url") or ""
    amazon_price_aed = db_product.get(
        "spotlight_amazon_price_aed"
    )

    if not source_url:
        update_product_status(
            asin=asin,
            status="error",
            error="Spotlight source_url (Link) eksik.",
        )

        logger.error(
            "%s: source_url eksik, içerik taranamadı.",
            asin,
        )

        return False

    if (
        not amazon_price_aed
        or float(amazon_price_aed) <= 0
    ):
        update_product_status(
            asin=asin,
            status="error",
            error=(
                "spotlight_amazon_price_aed eksik/geçersiz."
            ),
        )

        logger.error(
            "%s: spotlight_amazon_price_aed eksik/geçersiz.",
            asin,
        )

        return False

    content = scrape_content_only(
        page=page,
        asin=asin,
        url=source_url,
    )

    if content["status"] != "ok":
        update_product_status(
            asin=asin,
            status="error",
            error=(
                "İçerik bulunamadı (content_missing) — "
                "sayfa 404 olabilir veya ürün kaldırılmış."
            ),
        )

        logger.error(
            "%s: içerik bulunamadı (%s).",
            asin,
            source_url,
        )

        return False

    pricing = calculate_spotlight_selling_price(
        float(amazon_price_aed)
    )

    scraped_product: dict[str, Any] = {
        "asin": asin,
        "title": content["title"],
        "brand": content["brand"],
        "marketplace": "AE",
        "source_url": source_url,
        "bullets": content["bullets"],
        "description": content["description"],
        "images": content["images"],
        "shopify_price_aed": pricing["shopify_price_aed"],
    }

    save_scraped_product(scraped_product)

    update_product_status(
        asin=asin,
        status="ready_for_shopify",
    )

    print(
        f"{asin}: içerik tarandı, "
        f"shopify_price_aed={pricing['shopify_price_aed']}"
    )

    logger.info(
        "%s: içerik tarandı, shopify_price_aed=%s",
        asin,
        pricing["shopify_price_aed"],
    )

    return True


def main() -> None:
    initialize_database()
    migrate_product_table()

    recovered_count = recover_processing_products()

    if recovered_count:
        print(
            "Yarım kalan ürünler tekrar kuyruğa alındı:",
            recovered_count,
        )

    print("=" * 70)
    print("SOCCICA SPOTLIGHT PIPELINE")
    print("=" * 70)

    import_stats = import_spotlight_export()

    print(
        "Spotlight import istatistikleri:",
        import_stats,
    )

    logger.info(
        "Spotlight pipeline başlıyor. import_stats=%s",
        import_stats,
    )

    print_status_summary()

    pending_asins = get_spotlight_priced_asins(
        limit=SPOTLIGHT_BATCH_SIZE,
    )

    if not pending_asins:
        print(
            "\nİçerik taranacak spotlight_priced ASIN "
            "bulunamadı."
        )

        return

    success_count = 0
    error_count = 0

    with sync_playwright() as playwright:
        browser = create_browser(playwright)
        context = create_context(browser)
        page = context.new_page()

        try:
            for index, asin in enumerate(
                pending_asins,
                start=1,
            ):
                print("\n" + "=" * 70)
                print(
                    f"ASIN {index}/{len(pending_asins)}: "
                    f"{asin}"
                )
                print("=" * 70)

                try:
                    if process_spotlight_asin(
                        page,
                        asin,
                    ):
                        success_count += 1
                    else:
                        error_count += 1

                except Exception as error:
                    error_text = str(error)

                    update_product_status(
                        asin=asin,
                        status="error",
                        error=error_text,
                    )

                    print(
                        "ASIN işleme hatası:",
                        error_text,
                    )

                    logger.error(
                        "%s işleme hatası: %s",
                        asin,
                        error_text,
                        exc_info=True,
                    )

                    error_count += 1

        finally:
            try:
                context.close()
            except Exception:
                pass

            try:
                browser.close()
            except Exception:
                pass

    print("\n" + "=" * 70)
    print("SPOTLIGHT İÇERİK TARAMASI TAMAMLANDI")
    print("=" * 70)
    print("Başarılı:", success_count)
    print("Hatalı:", error_count)

    logger.info(
        "Spotlight pipeline tamamlandı. "
        "basarili=%d hatali=%d",
        success_count,
        error_count,
    )

    print_status_summary()


if __name__ == "__main__":
    main()
