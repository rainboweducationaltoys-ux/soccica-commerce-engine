import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from config import is_dry_run
from database import get_status_summary, initialize_database
from logging_setup import configure_logging


load_dotenv()

logger = configure_logging("soccica.spotlight_run_all")


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
    print(
        "Spotlight fiyatlandı:",
        summary.get("spotlight_priced", 0),
    )
    print(
        "Shopify için hazır:",
        summary.get("ready_for_shopify", 0),
    )
    print("Yayınlanan:", summary.get("published", 0))
    print("Atlanan:", summary.get("skipped", 0))
    print(
        "Tekrar denenecek:",
        summary.get("retry", 0),
    )
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

    print_summary("BAŞLANGIÇ DURUMU")

    print("\n" + "!" * 70)
    if is_dry_run():
        print(
            "DRY RUN — Shopify'a hiçbir gerçek yazma "
            "işlemi yapılmayacak."
        )
    else:
        print(
            "LIVE ÇALIŞMA — Shopify'a GERÇEK yazma "
            "işlemi yapılacak."
        )
    print("!" * 70)

    run_script(
        title=(
            "1/2 — SPOTLIGHT IMPORT + FİYATLANDIRMA + "
            "İÇERİK TARAMA"
        ),
        script_name="run_spotlight_pipeline.py",
    )

    print_summary("SPOTLIGHT PIPELINE SONRASI")

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
        sys.exit(1)
