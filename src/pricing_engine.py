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
    if landed_cost_aed <= 0:
        raise ValueError(
            "Landed cost sıfırdan büyük olmalıdır."
        )

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
            "Kâr marjı ve ödeme komisyonu toplamı "
            "%100'den küçük olmalıdır."
        )

    calculated_price = operational_cost / denominator
    final_price = round_shopify_price(calculated_price)

    payment_fee_aed = (
        final_price * payment_fee_rate
    )

    estimated_gross_profit = (
        final_price
        - landed_cost_aed
        - currency_buffer
        - return_risk
        - UAE_LAST_MILE_COST_AED
        - payment_fee_aed
    )

    return {
        "target_margin_percent": round(
            TARGET_MARGIN_PERCENT,
            2,
        ),
        "payment_fee_percent": round(
            PAYMENT_FEE_PERCENT,
            2,
        ),
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
        "payment_fee_aed": round(
            payment_fee_aed,
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
            estimated_gross_profit,
            2,
        ),
    }


def main() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Girdi dosyası bulunamadı: {INPUT_FILE}"
        )

    dataframe = pd.read_csv(INPUT_FILE)

    if dataframe.empty:
        print("Fiyatlandırılacak ürün bulunamadı.")
        return

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

    result_df = pd.DataFrame(pricing_rows)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
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


if __name__ == "__main__":
    main()