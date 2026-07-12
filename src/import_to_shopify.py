import csv

import pandas as pd

from shopify import create_html_description
from shopify_api import create_draft_product


INPUT_FILE = "output/amazon_products.csv"
INPUT_COLUMNS = [
    "asin",
    "url",
    "title",
    "price",
    "brand",
    "bullet_1",
    "bullet_2",
    "bullet_3",
    "bullet_4",
    "bullet_5",
    "description",
    "images",
    "downloaded_images",
]


def split_images(value: str) -> list[str]:
    if not value or pd.isna(value):
        return []

    return [
        image.strip()
        for image in str(value).split("|")
        if image.strip()
    ]


def split_bullets(row: pd.Series) -> list[str]:
    bullets = []

    for index in range(1, 6):
        value = row.get(f"bullet_{index}", "")

        if pd.notna(value) and str(value).strip():
            bullets.append(str(value).strip())

    return bullets


def load_products_dataframe() -> pd.DataFrame:
    rows: list[dict[str, str]] = []

    with open(INPUT_FILE, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(
            file,
            fieldnames=INPUT_COLUMNS,
            restkey="_extra",
            restval="",
        )

        next(reader, None)

        for row in reader:
            rows.append(
                {
                    column: row.get(column, "")
                    for column in INPUT_COLUMNS
                }
            )

    return pd.DataFrame(rows, columns=INPUT_COLUMNS)


def main() -> None:
    dataframe = load_products_dataframe()

    if dataframe.empty:
        print("Amazon ürün dosyasında ürün bulunamadı.")
        return

    row = dataframe.iloc[0]

    title = str(row.get("title", "")).strip()
    brand = str(row.get("brand", "")).strip() or "Soccica"
    category = str(row.get("category", "")).strip()
    description = str(row.get("description", "")).strip()

    bullets = split_bullets(row)
    images = split_images(row.get("images", ""))

    description_html = create_html_description(
        bullets=bullets,
        description=description,
    )

    tags = [
        "Amazon Import",
        brand,
    ]

    if category:
        tags.append(category)

    product = create_draft_product(
        title=title,
        description_html=description_html,
        vendor=brand,
        product_type=category or "Toys",
        tags=tags,
        image_urls=images,
    )

    print("=" * 60)
    print("Gerçek Amazon ürünü Shopify'a gönderildi")
    print("=" * 60)
    print("ID:", product["id"])
    print("Başlık:", product["title"])
    print("Handle:", product["handle"])
    print("Durum:", product["status"])


if __name__ == "__main__":
    main()