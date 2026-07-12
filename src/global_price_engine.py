import math
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv


load_dotenv()


BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_FILE = (
    BASE_DIR
    / "output"
    / "global_prices"
    / "best_marketplace_offers.csv"
)

OUTPUT_FILE = (
    BASE_DIR
    / "output"
    / "global_prices"
    / "priced_products.csv"
)


TARGET_MARGIN_PERCENT = float(
    os.getenv("TARGET_MARGIN_PERCENT", "30")
)

PAYMENT_FEE_PERCENT = float(
    os.getenv("PAYMENT_FEE_PERCENT", "3")
)

RETURN_RISK_PERCENT = float(
    os.getenv("RETURN_RISK_PERCENT", "5")
)

CURRENCY_BUFFER_PERCENT = float(
    os.getenv("CURRENCY_BUFFER_PERCENT", "3")
)

UAE_LAST_MILE_COST_AED = float(
    os.getenv("UAE_LAST_MILE_COST_AED", "20")
)


def round_shopify_price(price: float) -> float:
    rounded = math.ceil(price / 10) * 10

    return float(rounded - 1)


def calculate_selling_price(
    landed_cost_aed: float,
) -> dict[str, float]:
    currency_buffer = (
        landed_cost_aed
        * CURRENCY_BUFFER_PERCENT
        / 100
    )

    return_risk = (
        landed_cost_aed
        * RETURN_RISK_PERCENT
        / 100
    )

    operational_cost = (
        landed_cost_aed
        + currency_buffer
        + return_risk
        + UAE_LAST_MILE_COST_AED
    )

    margin_rate = TARGET_MARGIN_PERCENT / 100
    payment_fee_rate = PAYMENT_FEE_PERCENT / 100

    denominator = (
        1
        - margin_rate
        - payment_fee_rate
    )

    if denominator <= 0:
        raise ValueError(
            "Margin ve ödeme komisyonu toplamı %100'den küçük olmalı."
        )

    calculated_price = operational_cost / denominator

    final_price = round_shopify_price(
        calculated_price
    )

    gross_profit = (
        final_price
        - landed_cost_aed
        - currency_buffer
        - return_risk
        - UAE_LAST_MILE_COST_AED
        - final_price * payment_fee_rate
    )

    return {
        "currency_buffer_aed": round(
            currency_buffer,
            2,
        ),
        "return_risk_aed": round(
            return_risk,
            2,
        ),
        "last_mile_aed": round(
            UAE_LAST_MILE_COST_AED,
            2,
        ),
        "calculated_price_aed": round(
            calculated_price,
            2,
        ),
        "shopify_price_aed": round(
            final_price,
            2,
        ),
        "estimated_gross_profit_aed": round(
            gross_profit,
            2,
        ),
    }


def main() -> None:
    dataframe = pd.read_csv(INPUT_FILE)

    pricing_rows = []

    for _, row in dataframe.iterrows():
        landed_cost = float(
            row["landed_cost_aed"]
        )

        pricing = calculate_selling_price(
            landed_cost
        )

        result = row.to_dict()
        result.update(pricing)

        pricing_rows.append(result)

    result_df = pd.DataFrame(
        pricing_rows
    )

    result_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("=" * 70)
    print("Soccica fiyatlandırma tamamlandı")
    print("=" * 70)
    print("Ürün sayısı:", len(result_df))
    print("Dosya:", OUTPUT_FILE)

    columns = [
        "asin",
        "marketplace",
        "landed_cost_aed",
        "shopify_price_aed",
        "estimated_gross_profit_aed",
    ]

    print(
        result_df[columns].to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()