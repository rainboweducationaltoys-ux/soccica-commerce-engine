import json
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from browser import create_browser, create_context
from database import (
    add_asins,
    get_next_pending_asins,
    get_status_summary,
    initialize_database,
    recover_processing_products,
    save_marketplace_offer,
    update_product_status,
)
from marketplace_scraper import MARKETPLACES
from pricing_engine import calculate_selling_price
from product_engine import scrape_complete_offer
from product_store import (
    migrate_product_table,
    save_scraped_product,
)


load_dotenv()


BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_FILE = (
    BASE_DIR
    / "input"
    / "asin_spotlight.txt"
)

TEST_INPUT_FILE = (
    BASE_DIR
    / "input"
    / "test_asins.txt"
)

OUTPUT_DIR = (
    BASE_DIR
    / "output"
    / "global_prices"
)

ALL_OFFERS_FILE = (
    OUTPUT_DIR
    / "all_marketplace_offers.csv"
)

FINAL_PRODUCTS_FILE = (
    OUTPUT_DIR
    / "final_products.csv"
)

ERROR_FILE = (
    OUTPUT_DIR
    / "pipeline_errors.csv"
)

BATCH_SIZE = int(
    os.getenv("BATCH_SIZE", "100")
)

PAGE_WAIT_SECONDS = float(
    os.getenv("PAGE_WAIT_SECONDS", "2")
)

EXPORT_CSV = (
    os.getenv("EXPORT_CSV", "false").lower() == "true"
)

DRY_RUN = (
    os.getenv("DRY_RUN", "false").lower() == "true"
)


def safe_text(value: Any) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    return str(value).strip()


def load_asins_from_file(
    path: Path = INPUT_FILE,
) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(
            f"ASIN dosyası bulunamadı: {path}"
        )

    asins: list[str] = []
    seen: set[str] = set()

    with path.open(
        "r",
        encoding="utf-8-sig",
    ) as file:
        for line in file:
            value = line.strip().upper()

            if not value:
                continue

            if value == "ASIN":
                continue

            # Satırda başlık, virgül veya tab varsa yalnızca
            # ilk alanı ASIN olarak kullan.
            asin = (
                value
                .split("\t")[0]
                .split(",")[0]
                .strip()
            )

            if len(asin) != 10:
                continue

            if asin in seen:
                continue

            seen.add(asin)
            asins.append(asin)

    return asins


def flatten_offer(
    offer: dict[str, Any],
) -> dict[str, Any]:
    row = offer.copy()

    row["bullets"] = json.dumps(
        offer.get("bullets", []),
        ensure_ascii=False,
    )

    row["images"] = " | ".join(
        offer.get("images", [])
    )

    return row


def append_csv_row(
    file_path: Path,
    row: dict[str, Any],
) -> None:
    file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    pd.DataFrame([row]).to_csv(
        file_path,
        mode="a",
        header=not file_path.exists(),
        index=False,
        encoding="utf-8-sig",
    )


def select_best_offer(
    offers: list[dict[str, Any]],
) -> dict[str, Any] | None:
    eligible_offers = [
        offer
        for offer in offers
        if offer.get("eligible") is True
        and float(
            offer.get("landed_cost_aed", 0) or 0
        ) > 0
    ]

    if not eligible_offers:
        return None

    return min(
        eligible_offers,
        key=lambda offer: float(
            offer["landed_cost_aed"]
        ),
    )


def build_final_product(
    best_offer: dict[str, Any],
) -> dict[str, Any]:
    landed_cost = float(
        best_offer["landed_cost_aed"]
    )

    pricing = calculate_selling_price(
        landed_cost
    )

    result = flatten_offer(best_offer)
    result.update(pricing)

    return result


def print_status_summary() -> None:
    summary = get_status_summary()

    print("\n" + "-" * 70)
    print("VERİTABANI DURUMU")
    print("-" * 70)
    print("Toplam:", summary.get("total", 0))
    print("Bekleyen:", summary.get("pending", 0))
    print("Tekrar denenecek:", summary.get("retry", 0))
    print(
        "Shopify için hazır:",
        summary.get("ready_for_shopify", 0),
    )
    print(
        "Yayınlanan:",
        summary.get("published", 0),
    )
    print("Hatalı:", summary.get("error", 0))
    print("-" * 70)


def process_asin(
    page,
    asin: str,
) -> dict[str, Any] | None:
    update_product_status(
        asin=asin,
        status="processing",
    )

    asin_offers: list[dict[str, Any]] = []

    for marketplace in MARKETPLACES:
        try:
            offer = scrape_complete_offer(
                page=page,
                asin=asin,
                marketplace=marketplace,
            )

            asin_offers.append(offer)

            save_marketplace_offer(offer)

            if EXPORT_CSV:
                append_csv_row(
                    ALL_OFFERS_FILE,
                    flatten_offer(offer),
                )

            print(
                f"{marketplace.code} durum:",
                offer.get("status", ""),
            )

            print(
                f"{marketplace.code} landed cost:",
                offer.get("landed_cost_aed", 0),
            )

        except Exception as error:
            error_text = str(error)

            failed_offer = {
                "asin": asin,
                "marketplace": marketplace.code,
                "status": "error",
                "source_url": "",
                "item_price_aed": 0,
                "extra_charges_aed": 0,
                "landed_cost_aed": 0,
                "availability": "",
                "title": "",
                "error": error_text,
            }

            save_marketplace_offer(
                failed_offer
            )

            append_csv_row(
                ERROR_FILE,
                {
                    "asin": asin,
                    "marketplace": marketplace.code,
                    "error": error_text,
                },
            )

            print(
                f"{marketplace.code} hata:",
                error_text,
            )

        time.sleep(PAGE_WAIT_SECONDS)

    best_offer = select_best_offer(
        asin_offers
    )

    if best_offer is None:
        update_product_status(
            asin=asin,
            status="error",
            error=(
                "Dubai'ye gönderilebilen ve tam maliyeti "
                "hesaplanabilen teklif bulunamadı."
            ),
        )

        return None

    final_product = build_final_product(
        best_offer
    )

    scraped_product = {
        **final_product,
        **best_offer,
    }

    save_scraped_product(scraped_product)

    update_product_status(
        asin=asin,
        status="ready_for_shopify",
    )

    if EXPORT_CSV:
        append_csv_row(
            FINAL_PRODUCTS_FILE,
            final_product,
        )

    return final_product


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    initialize_database()
    migrate_product_table()

    recovered_count = (
        recover_processing_products()
    )

    if recovered_count:
        print(
            "Yarım kalan ürünler tekrar kuyruğa alındı:",
            recovered_count,
        )

    asin_input_file = INPUT_FILE

    if DRY_RUN and TEST_INPUT_FILE.exists():
        asin_input_file = TEST_INPUT_FILE

        print(
            "DRY_RUN aktif — test ASIN listesi kullanılıyor:",
            TEST_INPUT_FILE,
        )

    file_asins = load_asins_from_file(
        asin_input_file
    )

    inserted_count = add_asins(
        file_asins
    )

    print("=" * 70)
    print("SOCCICA SQLITE PRODUCT PIPELINE")
    print("=" * 70)
    print(
        "Dosyadaki benzersiz ASIN:",
        len(file_asins),
    )
    print(
        "Veritabanına yeni eklenen:",
        inserted_count,
    )
    print(
        "Parti büyüklüğü:",
        BATCH_SIZE,
    )

    print_status_summary()

    pending_asins = get_next_pending_asins(
        limit=BATCH_SIZE,
    )

    if not pending_asins:
        print(
            "\nİşlenecek pending veya retry ASIN bulunamadı."
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
                    final_product = process_asin(
                        page=page,
                        asin=asin,
                    )

                    if final_product is None:
                        error_count += 1
                        print(
                            "Uygun teklif bulunamadı."
                        )
                        continue

                    success_count += 1

                    print(
                        "Seçilen marketplace:",
                        final_product.get(
                            "marketplace",
                            "",
                        ),
                    )

                    print(
                        "Landed cost:",
                        final_product.get(
                            "landed_cost_aed",
                            0,
                        ),
                    )

                    print(
                        "Shopify fiyatı:",
                        final_product.get(
                            "shopify_price_aed",
                            0,
                        ),
                    )

                except KeyboardInterrupt:
                    print(
                        "\nİşlem kullanıcı tarafından durduruldu."
                    )

                    update_product_status(
                        asin=asin,
                        status="retry",
                        error=(
                            "İşlem kullanıcı tarafından "
                            "durduruldu."
                        ),
                    )

                    raise

                except Exception as error:
                    error_text = str(error)

                    update_product_status(
                        asin=asin,
                        status="retry",
                        error=error_text,
                    )

                    append_csv_row(
                        ERROR_FILE,
                        {
                            "asin": asin,
                            "marketplace": "",
                            "error": error_text,
                        },
                    )

                    error_count += 1

                    print(
                        "ASIN işleme hatası:",
                        error_text,
                    )

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
    print("PARTİ TAMAMLANDI")
    print("=" * 70)
    print("Başarılı:", success_count)
    print("Hatalı:", error_count)

    print_status_summary()

    remaining_summary = get_status_summary()

    remaining_count = (
        remaining_summary.get("pending", 0)
        + remaining_summary.get("retry", 0)
    )

    if remaining_count > 0:
        print(
            "\nKalan ürün:",
            remaining_count,
        )
        print(
            "Aynı komutu tekrar çalıştırdığında "
            "sonraki partiden devam edecek."
        )
    else:
        print(
            "\nAmazon tarama kuyruğundaki tüm "
            "ürünler tamamlandı."
        )


if __name__ == "__main__":
    main()