import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

from database import get_connection
from logging_setup import configure_logging
from shopify_api import graphql_request


load_dotenv()

logger = configure_logging("soccica.activator")

BASE_DIR = Path(__file__).resolve().parent.parent

ACTIVATION_LOG_FILE = (
    BASE_DIR
    / "output"
    / "global_prices"
    / "shopify_activation_log.csv"
)

ACTIVATE_PARALLEL_WORKERS = int(
    os.getenv("ACTIVATE_PARALLEL_WORKERS", "4")
)

STATUS_CHECK_BATCH_SIZE = 100

ERROR_CHECK_WINDOW = int(
    os.getenv("ACTIVATE_ERROR_CHECK_WINDOW", "250")
)

ERROR_RATE_THRESHOLD = float(
    os.getenv("ACTIVATE_ERROR_RATE_THRESHOLD", "0.10")
)

LOG_EVERY = int(
    os.getenv("ACTIVATE_LOG_EVERY", "250")
)

RETRY_MAX_ATTEMPTS = int(
    os.getenv("ACTIVATE_RETRY_MAX_ATTEMPTS", "3")
)

RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectTimeout,
    requests.exceptions.ReadTimeout,
    requests.exceptions.ConnectionError,
)

csv_lock = threading.Lock()
counter_lock = threading.Lock()


def call_with_retry(
    func: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    last_error: Exception | None = None

    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            return func(*args, **kwargs)
        except RETRYABLE_EXCEPTIONS as error:
            last_error = error

            if attempt < RETRY_MAX_ATTEMPTS:
                time.sleep(2 ** attempt)

    raise last_error


def get_candidate_products() -> list[dict[str, str]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT asin, shopify_product_id
            FROM products
            WHERE status = 'published'
              AND shopify_product_id IS NOT NULL
              AND shopify_product_id != ''
            ORDER BY updated_at ASC
            """
        ).fetchall()

    return [
        {
            "asin": row["asin"],
            "shopify_product_id": row["shopify_product_id"],
        }
        for row in rows
    ]


def chunked(
    items: list[Any],
    size: int,
) -> list[list[Any]]:
    return [
        items[start:start + size]
        for start in range(0, len(items), size)
    ]


def fetch_live_activation_state(
    product_ids: list[str],
) -> dict[str, dict[str, Any]]:
    query = """
    query CheckStatus($ids: [ID!]!) {
      nodes(ids: $ids) {
        ... on Product {
          id
          status
          resourcePublicationsV2(first: 10) {
            nodes {
              isPublished
              publication { name }
            }
          }
        }
      }
    }
    """

    state: dict[str, dict[str, Any]] = {}

    for batch in chunked(
        product_ids,
        STATUS_CHECK_BATCH_SIZE,
    ):
        payload = call_with_retry(
            graphql_request,
            query,
            {"ids": batch},
        )

        for node in payload.get("data", {}).get("nodes", []):
            if not node or not node.get("id"):
                continue

            online_store_published = any(
                publication_node.get("isPublished")
                and publication_node.get(
                    "publication", {}
                ).get("name")
                == "Online Store"
                for publication_node in (
                    node
                    .get("resourcePublicationsV2", {})
                    .get("nodes", [])
                )
            )

            state[node["id"]] = {
                "status": node.get("status", ""),
                "online_store_published":
                    online_store_published,
            }

    return state


def needs_activation(
    state: dict[str, Any] | None,
) -> bool:
    if state is None:
        return False

    return (
        state.get("status") != "ACTIVE"
        or not state.get("online_store_published")
    )


def get_online_store_publication_id() -> str:
    query = """
    query Publications {
      publications(first: 10) {
        nodes {
          id
          name
        }
      }
    }
    """

    payload = graphql_request(query)

    nodes = (
        payload
        .get("data", {})
        .get("publications", {})
        .get("nodes", [])
    )

    for node in nodes:
        if node.get("name") == "Online Store":
            return node["id"]

    raise RuntimeError(
        "Shopify mağazasında 'Online Store' satış kanalı bulunamadı."
    )


def append_log_row(
    row: dict[str, Any],
) -> None:
    ACTIVATION_LOG_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with csv_lock:
        pd.DataFrame([row]).to_csv(
            ACTIVATION_LOG_FILE,
            mode="a",
            header=not ACTIVATION_LOG_FILE.exists(),
            index=False,
            encoding="utf-8-sig",
        )


def activate_and_publish(
    product_id: str,
    online_store_publication_id: str,
) -> None:
    activate_mutation = """
    mutation ActivateProduct($input: ProductUpdateInput!) {
      productUpdate(product: $input) {
        product { id status }
        userErrors { field message }
      }
    }
    """

    result = call_with_retry(
        graphql_request,
        activate_mutation,
        {
            "input": {
                "id": product_id,
                "status": "ACTIVE",
            },
        },
    )

    user_errors = (
        result
        .get("data", {})
        .get("productUpdate", {})
        .get("userErrors", [])
    )

    if user_errors:
        raise RuntimeError(
            "productUpdate hatası: "
            + " | ".join(
                error.get("message", "")
                for error in user_errors
            )
        )

    publish_mutation = """
    mutation PublishToChannel(
      $id: ID!
      $input: [PublicationInput!]!
    ) {
      publishablePublish(id: $id, input: $input) {
        publishable {
          ... on Product { id }
        }
        userErrors { field message }
      }
    }
    """

    result = call_with_retry(
        graphql_request,
        publish_mutation,
        {
            "id": product_id,
            "input": [
                {
                    "publicationId":
                        online_store_publication_id,
                }
            ],
        },
    )

    user_errors = (
        result
        .get("data", {})
        .get("publishablePublish", {})
        .get("userErrors", [])
    )

    if user_errors:
        raise RuntimeError(
            "publishablePublish hatası: "
            + " | ".join(
                error.get("message", "")
                for error in user_errors
            )
        )


def main() -> None:
    print("=" * 70)
    print("LIVE — ACTIVATING PRODUCTS FOR PUBLIC SALE")
    print("=" * 70)
    print(
        "Bu script DRAFT durumundaki ürünleri ACTIVE yapıp "
        "Online Store kanalına yayınlayacak."
    )
    print(
        "Bu, bu projede ürünlerin ilk kez halka açık/satın "
        "alınabilir hale geldiği adımdır."
    )
    print("=" * 70)

    online_store_publication_id = (
        get_online_store_publication_id()
    )

    print(
        "Online Store publication ID:",
        online_store_publication_id,
    )

    candidates = get_candidate_products()

    print(
        f"\nYerel veritabanında {len(candidates)} ürün "
        "aday olarak bulundu (status='published', "
        "shopify_product_id mevcut)."
    )

    logger.info(
        "Aktivasyon başlıyor. aday_sayisi=%d",
        len(candidates),
    )

    if not candidates:
        print("İşlenecek aday ürün yok.")
        return

    product_ids = [
        candidate["shopify_product_id"]
        for candidate in candidates
    ]

    print(
        "\nCanlı Shopify durumları kontrol ediliyor "
        f"({len(product_ids)} ürün)..."
    )

    live_state = fetch_live_activation_state(product_ids)

    pending_candidates = [
        candidate
        for candidate in candidates
        if needs_activation(
            live_state.get(
                candidate["shopify_product_id"]
            )
        )
    ]

    already_done = len(candidates) - len(pending_candidates)

    print(
        f"Aktivasyon/yayın gereken: {len(pending_candidates)} "
        f"— zaten ACTIVE + Online Store'da yayında "
        f"(atlanacak): {already_done}"
    )

    logger.info(
        "Canlı durum kontrolü tamamlandı. gereken=%d "
        "zaten_tamam=%d",
        len(pending_candidates),
        already_done,
    )

    if not pending_candidates:
        print(
            "Aktifleştirilecek/yayınlanacak ürün yok. "
            "(Hepsi zaten ACTIVE + Online Store'da yayında.)"
        )
        return

    print(
        f"\nBaşlangıç sayısı: {len(pending_candidates)} ürün "
        "aktifleştirilecek/yayınlanacak.\n"
    )

    chunks = chunked(
        pending_candidates,
        max(
            1,
            -(
                -len(pending_candidates)
                // ACTIVATE_PARALLEL_WORKERS
            ),
        ),
    )

    print(
        f"Paralel worker sayısı: {len(chunks)} "
        f"(ACTIVATE_PARALLEL_WORKERS={ACTIVATE_PARALLEL_WORKERS})"
    )

    shared_counts = {
        "processed": 0,
        "errors": 0,
    }
    stop_event = threading.Event()

    def run_worker_with_shared_tracking(
        worker_id: int,
        products: list[dict[str, str]],
    ) -> dict[str, int]:
        prefix = f"[Worker {worker_id}]"

        counts = {"activated": 0, "error": 0}

        for index, product in enumerate(
            products,
            start=1,
        ):
            if stop_event.is_set():
                remaining = len(products) - index + 1

                print(
                    f"{prefix} hata eşiği aşıldığı için "
                    f"durduruldu, kalan {remaining} ürün "
                    "atlanıyor."
                )

                break

            asin = product["asin"]
            product_id = product["shopify_product_id"]
            errored = False

            try:
                activate_and_publish(
                    product_id,
                    online_store_publication_id,
                )

                append_log_row(
                    {
                        "asin": asin,
                        "shopify_product_id": product_id,
                        "result": "ACTIVATED",
                        "error": "",
                    }
                )

                counts["activated"] += 1

            except Exception as error:
                errored = True
                error_text = str(error)

                append_log_row(
                    {
                        "asin": asin,
                        "shopify_product_id": product_id,
                        "result": "ERROR",
                        "error": error_text,
                    }
                )

                logger.error(
                    "%s %s aktivasyon hatası: %s",
                    prefix,
                    asin,
                    error_text,
                    exc_info=True,
                )

                counts["error"] += 1

            with counter_lock:
                shared_counts["processed"] += 1

                if errored:
                    shared_counts["errors"] += 1

                processed = shared_counts["processed"]
                errors = shared_counts["errors"]

                if processed % LOG_EVERY == 0:
                    print(
                        f"\n[İlerleme] İşlenen: {processed}/"
                        f"{len(pending_candidates)} — "
                        f"Hatalı: {errors} "
                        f"({errors / processed:.1%})\n"
                    )

                    logger.info(
                        "İlerleme: islenen=%d hatali=%d",
                        processed,
                        errors,
                    )

                if (
                    processed >= ERROR_CHECK_WINDOW
                    and errors / processed
                    > ERROR_RATE_THRESHOLD
                    and not stop_event.is_set()
                ):
                    print(
                        "\n" + "!" * 70
                    )
                    print(
                        "HATA EŞİĞİ AŞILDI — "
                        f"{errors}/{processed} "
                        f"(%{errors / processed * 100:.1f}) "
                        f"hata, eşik %"
                        f"{ERROR_RATE_THRESHOLD * 100:.0f}. "
                        "Yeni ürün işlenmeyecek, mevcut "
                        "worker'lar bitiriyor."
                    )
                    print("!" * 70 + "\n")

                    logger.warning(
                        "Hata eşiği aşıldı: islenen=%d "
                        "hatali=%d oran=%.3f",
                        processed,
                        errors,
                        errors / processed,
                    )

                    stop_event.set()

        return counts

    with ThreadPoolExecutor(
        max_workers=len(chunks)
    ) as executor:
        futures = {
            executor.submit(
                run_worker_with_shared_tracking,
                worker_id,
                chunk,
            ): worker_id
            for worker_id, chunk in enumerate(
                chunks,
                start=1,
            )
        }

        total_activated = 0
        total_error = 0

        for future in as_completed(futures):
            worker_id = futures[future]

            try:
                counts = future.result()
            except Exception as error:
                counts = {"activated": 0, "error": 0}

                logger.error(
                    "[Worker %d] beklenmeyen hata: %s",
                    worker_id,
                    error,
                    exc_info=True,
                )

            total_activated += counts["activated"]
            total_error += counts["error"]

            print(
                f"[Worker {worker_id}] tamamlandı. "
                f"Aktif={counts['activated']} "
                f"Hatalı={counts['error']}"
            )

    print("\n" + "=" * 70)
    print("AKTİVASYON PARTİSİ TAMAMLANDI")
    print("=" * 70)
    print(
        "Zaten ACTIVE + Online Store'da yayında "
        "(atlandı):",
        already_done,
    )
    print("Yeni aktifleştirilen:", total_activated)
    print("Hatalı:", total_error)
    print(
        "Erken durduruldu mu:",
        stop_event.is_set(),
    )

    logger.info(
        "Aktivasyon tamamlandı. zaten_tamam=%d "
        "aktiflestirilen=%d hatali=%d erken_durdu=%s",
        already_done,
        total_activated,
        total_error,
        stop_event.is_set(),
    )


if __name__ == "__main__":
    main()
