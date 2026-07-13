import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from database import (
    get_status_summary,
    initialize_database,
)
from logging_setup import configure_logging


load_dotenv()

logger = configure_logging("soccica.run_all")


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
PYTHON = BASE_DIR / ".venv" / "bin" / "python"


def print_summary(title: str) -> None:
    summary = get_status_summary()

    logger.info("%s: %s", title, summary)

    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    print("Toplam:", summary.get("total", 0))
    print("Bekleyen:", summary.get("pending", 0))
    print("Tekrar denenecek:", summary.get("retry", 0))
    print("İşleniyor:", summary.get("processing", 0))
    print(
        "Shopify için hazır:",
        summary.get("ready_for_shopify", 0),
    )
    print("Yayınlanan:", summary.get("published", 0))
    print("Atlanan:", summary.get("skipped", 0))
    print("Hatalı:", summary.get("error", 0))
    print("=" * 70)


def run_script(
    title: str,
    script_name: str,
) -> None:
    script_path = SRC_DIR / script_name

    if not script_path.exists():
        raise FileNotFoundError(
            f"Script bulunamadı: {script_path}"
        )

    print("\n" + "#" * 70)
    print(title)
    print("#" * 70)

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SRC_DIR)

    result = subprocess.run(
        [
            str(PYTHON),
            str(script_path),
        ],
        cwd=BASE_DIR,
        env=environment,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{script_name} başarısız oldu. "
            f"Çıkış kodu: {result.returncode}"
        )


def has_remaining_amazon_work() -> bool:
    summary = get_status_summary()

    return (
        summary.get("pending", 0) > 0
        or summary.get("retry", 0) > 0
    )


def has_ready_shopify_products() -> bool:
    summary = get_status_summary()

    return (
        summary.get("ready_for_shopify", 0) > 0
    )


def main() -> None:
    if not PYTHON.exists():
        raise FileNotFoundError(
            f"Sanal ortam Python bulunamadı: {PYTHON}"
        )

    initialize_database()

    logger.info("run_all başlıyor.")

    print_summary("BAŞLANGIÇ DURUMU")

    run_script(
        title="1/2 — AMAZON GLOBAL PIPELINE",
        script_name="run_pipeline.py",
    )

    print_summary("AMAZON TARAMASI SONRASI")

    if has_ready_shopify_products():
        run_script(
            title="2/2 — SHOPIFY DRAFT PUBLISHER",
            script_name="publish_final_products.py",
        )
    else:
        print(
            "\nShopify için hazır ürün bulunmadığı için "
            "yayınlama adımı atlandı."
        )

    print_summary("ÇALIŞMA SONUCU")

    if has_remaining_amazon_work():
        print(
            "\nBekleyen ürünler var. Aynı komutu tekrar "
            "çalıştırdığında sonraki partiden devam eder."
        )
    else:
        print(
            "\nAmazon tarama kuyruğu tamamlandı."
        )

    if has_ready_shopify_products():
        print(
            "Shopify için hazır ürünler hâlâ var. "
            "PUBLISH_LIMIT değerini artırabilir veya "
            "komutu tekrar çalıştırabilirsin."
        )
    else:
        print(
            "Bu çalışma için Shopify yayınlama kuyruğu tamamlandı."
        )

    logger.info("run_all tamamlandı.")


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print(
            "\nİşlem kullanıcı tarafından durduruldu."
        )
        sys.exit(130)

    except Exception as error:
        print(f"\nHATA: {error}")

        logger.error(
            "run_all hatası: %s",
            error,
            exc_info=True,
        )

        sys.exit(1)