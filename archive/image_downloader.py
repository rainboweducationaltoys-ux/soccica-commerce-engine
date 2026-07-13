from pathlib import Path
from urllib.parse import urlparse

import requests

from config import IMAGES_DIR


def get_file_extension(url: str) -> str:
    path = urlparse(url).path.lower()

    for extension in [".jpg", ".jpeg", ".png", ".webp"]:
        if path.endswith(extension):
            return extension

    return ".jpg"


def download_product_images(product: dict, output_dir: Path | None = None) -> list[Path]:
    image_urls = product.get("images", []) or []
    if not image_urls:
        return []

    if output_dir is None:
        asin = (product.get("asin") or "product").strip() or "product"
        output_dir = IMAGES_DIR / asin

    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded_files: list[Path] = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/149.0.0.0 Safari/537.36"
        )
    }

    for index, image_url in enumerate(image_urls, start=1):
        try:
            extension = get_file_extension(image_url)
            filename = f"{index}{extension}"
            file_path = output_dir / filename

            response = requests.get(
                image_url,
                headers=headers,
                timeout=30,
            )

            response.raise_for_status()

            file_path.write_bytes(response.content)

            downloaded_files.append(str(file_path))

            print(f"Görsel indirildi: {filename}")

        except Exception as error:
            print(
                f"Görsel indirilemedi: {image_url} | {error}"
            )

    return downloaded_files