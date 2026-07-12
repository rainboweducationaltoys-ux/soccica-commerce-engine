import csv
import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_FILE = BASE_DIR / "output" / "amazon_products.csv"
OUTPUT_FILE = BASE_DIR / "output" / "competitor_analysis.csv"


def safe_text(value: Any) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    return str(value).strip()


def safe_float(value: Any) -> float:
    text = safe_text(value)

    if not text:
        return 0.0

    text = text.replace(",", "")

    match = re.search(r"-?\d+(?:\.\d+)?", text)

    if not match:
        return 0.0

    try:
        return float(match.group(0))
    except ValueError:
        return 0.0


def safe_int(value: Any) -> int:
    number = safe_float(value)

    if number < 0:
        return 0

    return int(number)


def normalize_availability(value: Any) -> str:
    text = safe_text(value).lower()

    if not text:
        return "unknown"

    out_of_stock_terms = [
        "currently unavailable",
        "out of stock",
        "temporarily out of stock",
        "unavailable",
    ]

    in_stock_terms = [
        "in stock",
        "available",
        "ships from",
        "delivery",
    ]

    if any(term in text for term in out_of_stock_terms):
        return "out_of_stock"

    if any(term in text for term in in_stock_terms):
        return "in_stock"

    return "unknown"


def parse_variation_count(value: Any) -> int:
    text = safe_text(value)

    if not text:
        return 0

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return 0

    if not isinstance(data, dict):
        return 0

    total = 0

    for options in data.values():
        if isinstance(options, list):
            total += len(options)

    return total


def calculate_review_strength(review_count: int) -> float:
    if review_count <= 0:
        return 0.0

    # Çok yüksek yorum sayılarının skoru orantısız büyütmesini engeller.
    return min(
        100.0,
        math.log10(review_count + 1) / 4 * 100,
    )


def calculate_demand_score(
    rating: float,
    review_count: int,
    availability: str,
) -> float:
    rating_score = min(max(rating / 5 * 100, 0), 100)
    review_score = calculate_review_strength(review_count)

    availability_score = {
        "in_stock": 100,
        "unknown": 50,
        "out_of_stock": 20,
    }.get(availability, 50)

    score = (
        rating_score * 0.40
        + review_score * 0.45
        + availability_score * 0.15
    )

    return round(score, 2)


def calculate_competition_score(
    rating: float,
    review_count: int,
    variation_count: int,
) -> float:
    rating_strength = min(max(rating / 5 * 100, 0), 100)
    review_strength = calculate_review_strength(review_count)

    variation_strength = min(
        variation_count / 20 * 100,
        100,
    )

    # Yüksek skor, rakibin daha güçlü olduğu anlamına gelir.
    score = (
        rating_strength * 0.30
        + review_strength * 0.55
        + variation_strength * 0.15
    )

    return round(score, 2)


def calculate_price_score(
    price: float,
    median_price: float,
) -> float:
    if price <= 0 or median_price <= 0:
        return 50.0

    ratio = price / median_price

    if 0.85 <= ratio <= 1.15:
        return 100.0

    if 0.70 <= ratio < 0.85:
        return 85.0

    if 1.15 < ratio <= 1.35:
        return 80.0

    if 0.50 <= ratio < 0.70:
        return 60.0

    if 1.35 < ratio <= 1.70:
        return 55.0

    return 35.0


def calculate_opportunity_score(
    demand_score: float,
    competition_score: float,
    price_score: float,
    data_quality_score: float,
) -> float:
    inverse_competition = 100 - competition_score

    score = (
        demand_score * 0.42
        + inverse_competition * 0.33
        + price_score * 0.15
        + data_quality_score * 0.10
    )

    return round(max(0, min(score, 100)), 2)


def calculate_data_quality_score(row: pd.Series) -> float:
    fields = [
        "title",
        "price",
        "brand",
        "rating",
        "review_count",
        "availability",
        "category",
        "images",
    ]

    present = 0

    for field in fields:
        if field in row and safe_text(row.get(field)):
            present += 1

    return round(present / len(fields) * 100, 2)


def create_recommendation(
    opportunity_score: float,
    demand_score: float,
    competition_score: float,
    data_quality_score: float,
) -> str:
    if data_quality_score < 50:
        return "MANUAL_REVIEW"

    if (
        opportunity_score >= 70
        and demand_score >= 60
        and competition_score <= 65
    ):
        return "STRONG_OPPORTUNITY"

    if opportunity_score >= 58:
        return "REVIEW_FOR_LISTING"

    if competition_score >= 75:
        return "HIGH_COMPETITION"

    return "LOW_PRIORITY"


def analyze_products(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy()

    working = dataframe.copy()

    working["price_numeric"] = working.get(
        "price",
        pd.Series(dtype=float),
    ).apply(safe_float)

    valid_prices = working.loc[
        working["price_numeric"] > 0,
        "price_numeric",
    ]

    median_price = (
        float(valid_prices.median())
        if not valid_prices.empty
        else 0.0
    )

    results: list[dict[str, Any]] = []

    for _, row in working.iterrows():
        price = safe_float(row.get("price"))
        rating = safe_float(row.get("rating"))
        review_count = safe_int(row.get("review_count"))

        availability = normalize_availability(
            row.get("availability")
        )

        variation_count = parse_variation_count(
            row.get("variations")
        )

        demand_score = calculate_demand_score(
            rating=rating,
            review_count=review_count,
            availability=availability,
        )

        competition_score = calculate_competition_score(
            rating=rating,
            review_count=review_count,
            variation_count=variation_count,
        )

        price_score = calculate_price_score(
            price=price,
            median_price=median_price,
        )

        data_quality_score = calculate_data_quality_score(row)

        opportunity_score = calculate_opportunity_score(
            demand_score=demand_score,
            competition_score=competition_score,
            price_score=price_score,
            data_quality_score=data_quality_score,
        )

        recommendation = create_recommendation(
            opportunity_score=opportunity_score,
            demand_score=demand_score,
            competition_score=competition_score,
            data_quality_score=data_quality_score,
        )

        results.append(
            {
                "asin": safe_text(row.get("asin")),
                "url": safe_text(row.get("url")),
                "title": safe_text(row.get("title")),
                "brand": safe_text(row.get("brand")),
                "category": safe_text(row.get("category")),
                "price": price,
                "median_price": round(median_price, 2),
                "rating": rating,
                "review_count": review_count,
                "availability": availability,
                "variation_count": variation_count,
                "demand_score": demand_score,
                "competition_score": competition_score,
                "price_score": round(price_score, 2),
                "data_quality_score": data_quality_score,
                "opportunity_score": opportunity_score,
                "recommendation": recommendation,
            }
        )

    result_df = pd.DataFrame(results)

    return result_df.sort_values(
        by=[
            "opportunity_score",
            "demand_score",
        ],
        ascending=[False, False],
    )


def load_input_dataframe() -> pd.DataFrame:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Amazon ürün dosyası bulunamadı: {INPUT_FILE}"
        )

    with INPUT_FILE.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))

    if not rows:
        return pd.DataFrame()

    header = [cell.strip() for cell in rows[0]]
    data_rows = rows[1:]

    normalized_rows: list[dict[str, Any]] = []

    for row in data_rows:
        if not row:
            continue

        row_dict: dict[str, Any] = {}
        for index, column in enumerate(header):
            value = row[index] if index < len(row) else ""
            row_dict[column] = value

        normalized_rows.append(row_dict)

    dataframe = pd.DataFrame(normalized_rows)

    if dataframe.empty:
        return dataframe

    dataframe.columns = [
        col.strip().lower().replace(" ", "_")
        for col in dataframe.columns
    ]

    return dataframe


def main() -> None:
    dataframe = load_input_dataframe()

    if dataframe.empty:
        print("amazon_products.csv içinde ürün bulunamadı.")
        return

    result = analyze_products(dataframe)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("=" * 60)
    print("Soccica Competitor Analyzer")
    print("=" * 60)
    print(f"Analiz edilen ürün: {len(result)}")
    print(f"Medyan fiyat: {result['median_price'].iloc[0]:.2f}")
    print(
        "Güçlü fırsat:",
        int(
            (
                result["recommendation"]
                == "STRONG_OPPORTUNITY"
            ).sum()
        ),
    )
    print(
        "İncelenecek:",
        int(
            (
                result["recommendation"]
                == "REVIEW_FOR_LISTING"
            ).sum()
        ),
    )
    print(
        "Yüksek rekabet:",
        int(
            (
                result["recommendation"]
                == "HIGH_COMPETITION"
            ).sum()
        ),
    )
    print(f"Dosya oluşturuldu: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()