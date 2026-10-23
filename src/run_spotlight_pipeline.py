import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from browser import create_browser, create_context
from config import is_dry_run
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

PARALLEL_WORKERS = int(
    os.getenv("PARALLEL_WORKERS", "3")
)

RETRY_MAX_ATTEMPTS = int(
    os.getenv("RETRY_MAX_ATTEMPTS", "3")
)

TRANSIENT_CONTENT_STATUSES = {
    "captcha",
    "page_error",
}


def split_into_chunks(
    items: list[str],
    chunk_count: int,
) -> list[list[str]]:
    if not items:
        return []

    chunk_count = max(
        1,
        min(chunk_count, len(items)),
    )

    base_size, remainder = divmod(
        len(items),
        chunk_count,
    )

    chunks: list[list[str]] = []
    start = 0

    for index in range(chunk_count):
        size = base_size + (
            1 if index < remainder else 0
        )

        chunks.append(
            items[start:start + size]
        )

        start += size

    return chunks


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
        "Spotlight tekrar denenecek:",
        summary.get("spotlight_retry", 0),
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
    attempts_before: int = 0,
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

    if content["status"] in TRANSIENT_CONTENT_STATUSES:
        if attempts_before < RETRY_MAX_ATTEMPTS:
            update_product_status(
                asin=asin,
                status="spotlight_retry",
                error=(
                    "Geçici hata (CAPTCHA/sayfa hatası): "
                    + content["status"]
                ),
            )

            logger.warning(
                "%s: geçici hata (%s), spotlight_retry olarak "
                "işaretlendi (deneme %d/%d).",
                asin,
                content["status"],
                attempts_before + 1,
                RETRY_MAX_ATTEMPTS,
            )
        else:
            permanent_error = (
                "CAPTCHA/page hatası nedeniyle "
                f"{RETRY_MAX_ATTEMPTS} denemede başarısız, "
                "kalıcı hata olarak işaretlendi."
            )

            update_product_status(
                asin=asin,
                status="error",
                error=permanent_error,
            )

            logger.warning(
                "%s: %s",
                asin,
                permanent_error,
            )

        return False

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


def run_worker(
    worker_id: int,
    asins: list[str],
    stop_event: threading.Event,
) -> tuple[int, int]:
    prefix = f"[Worker {worker_id}]"

    success_count = 0
    error_count = 0

    with sync_playwright() as playwright:
        browser = create_browser(playwright)
        context = create_context(browser)
        page = context.new_page()

        try:
            for index, asin in enumerate(
                asins,
                start=1,
            ):
                if stop_event.is_set():
                    remaining = len(asins) - index + 1

                    print(
                        f"{prefix} durduruldu, kalan "
                        f"{remaining} ASIN atlanıyor."
                    )

                    logger.info(
                        "%s durduruldu, kalan %d ASIN "
                        "atlanıyor.",
                        prefix,
                        remaining,
                    )

                    break

                print(
                    f"\n{'=' * 70}\n"
                    f"{prefix} ASIN {index}/{len(asins)}: "
                    f"{asin}\n"
                    f"{'=' * 70}"
                )

                current_product = get_product_by_asin(asin)

                attempts_before = (
                    current_product.get("attempt_count", 0)
                    if current_product
                    else 0
                )

                try:
                    if process_spotlight_asin(
                        page,
                        asin,
                        attempts_before=attempts_before,
                    ):
                        success_count += 1
                    else:
                        error_count += 1

                except Exception as error:
                    error_text = str(error)

                    if attempts_before < RETRY_MAX_ATTEMPTS:
                        update_product_status(
                            asin=asin,
                            status="spotlight_retry",
                            error=error_text,
                        )

                        logger.warning(
                            "%s %s: işleme hatası (%s), "
                            "spotlight_retry olarak işaretlendi "
                            "(deneme %d/%d).",
                            prefix,
                            asin,
                            error_text,
                            attempts_before + 1,
                            RETRY_MAX_ATTEMPTS,
                        )
                    else:
                        permanent_error = (
                            f"{RETRY_MAX_ATTEMPTS} denemede "
                            f"başarısız (son hata: {error_text}), "
                            "kalıcı hata olarak işaretlendi."
                        )

                        update_product_status(
                            asin=asin,
                            status="error",
                            error=permanent_error,
                        )

                        logger.warning(
                            "%s %s: %s",
                            prefix,
                            asin,
                            permanent_error,
                        )

                    print(
                        f"{prefix} ASIN işleme hatası: "
                        f"{error_text}"
                    )

                    logger.error(
                        "%s %s işleme hatası: %s",
                        prefix,
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

    return success_count, error_count


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

    chunks = split_into_chunks(
        pending_asins,
        PARALLEL_WORKERS,
    )

    print(
        f"\nParalel worker sayısı: {len(chunks)} "
        f"(PARALLEL_WORKERS={PARALLEL_WORKERS})"
    )

    for worker_id, chunk in enumerate(
        chunks,
        start=1,
    ):
        print(f"  Worker {worker_id}: {len(chunk)} ASIN")

    logger.info(
        "Paralel worker dağılımı: %s",
        [len(chunk) for chunk in chunks],
    )

    success_count = 0
    error_count = 0
    stop_event = threading.Event()
    interrupted = False
    reported: set[Any] = set()

    with ThreadPoolExecutor(
        max_workers=len(chunks)
    ) as executor:
        futures = {
            executor.submit(
                run_worker,
                worker_id,
                chunk,
                stop_event,
            ): worker_id
            for worker_id, chunk in enumerate(
                chunks,
                start=1,
            )
        }

        def collect(future) -> None:
            nonlocal success_count, error_count

            if future in reported:
                return

            reported.add(future)

            try:
                worker_success, worker_error = (
                    future.result()
                )
            except Exception as error:
                worker_success, worker_error = 0, 0

                logger.error(
                    "[Worker %d] beklenmeyen hata: %s",
                    futures[future],
                    error,
                    exc_info=True,
                )

            success_count += worker_success
            error_count += worker_error

            print(
                f"[Worker {futures[future]}] tamamlandı. "
                f"Başarılı={worker_success} "
                f"Hatalı={worker_error}"
            )

        try:
            for future in as_completed(futures):
                collect(future)

        except KeyboardInterrupt:
            interrupted = True

            print(
                "\nİşlem kullanıcı tarafından durduruldu. "
                "Çalışan worker'ların bitirmesi bekleniyor..."
            )

            logger.info(
                "İşlem kullanıcı tarafından durduruldu, "
                "worker'lar bekleniyor."
            )

            stop_event.set()

            for future in futures:
                collect(future)

    if interrupted:
        raise KeyboardInterrupt()

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
