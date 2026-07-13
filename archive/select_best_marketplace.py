import re
from pathlib import Path
from typing import Any

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_FILE = (
    BASE_DIR
    / "output"
    / "global_prices"
    / "marketplace_prices.csv"
)

OUTPUT_FILE = (
    BASE_DIR
    / "output"
    / "global_prices"
    / "best_marketplace_offers.csv"
)

REJECTED_FILE = (
    BASE_DIR
    / "output"
    / "global_prices"
    / "rejected_marketplace_offers.csv"
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


def extract_aed_amount(value: Any) -> float:
    text = safe_text(value)

    if not text:
        return 0.0

    # AED 1,234.56 veya AED123.45
    match = re.search(
        r"AED\s*([\d,]+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )

    if not match:
        return 0.0

    return float(
        match.group(1).replace(",", "")
    )


def calculate_extra_charges(row: pd.Series) -> tuple[float, str]:
    import_text = safe_text(
        row.get("import_fees")
    )

    shipping_text = safe_text(
        row.get("shipping_to_uae")
    )

    import_amount = extract_aed_amount(import_text)
    shipping_amount = extract_aed_amount(shipping_text)

    # "Shipping & Import Charges" toplam ücrettir.
    if import_amount > 0:
        return import_amount, "combined_shipping_import"

    # Yalnızca kargo bedeli açıkça görünüyorsa onu kullan.
    if shipping_amount > 0:
        return shipping_amount, "shipping_only"

    return 0.0, "charges_missing"


def main() -> None:
    dataframe = pd.read_csv(INPUT_FILE)

    dataframe["item_price_aed"] = dataframe[
        "price_text"
    ].apply(extract_aed_amount)

    charge_results = dataframe.apply(
        calculate_extra_charges,
        axis=1,
    )

    dataframe["extra_charges_aed"] = [
        result[0]
        for result in charge_results
    ]

    dataframe["charges_type"] = [
        result[1]
        for result in charge_results
    ]

    dataframe["landed_cost_aed"] = (
        dataframe["item_price_aed"]
        + dataframe["extra_charges_aed"]
    ).round(2)

    # Yalnızca:
    # - Dubai'ye gönderilebilen
    # - ürün fiyatı bulunan
    # - kargo/ithalat ücreti bulunan
    # teklifler final karşılaştırmaya girer.
    eligible = dataframe[
        (dataframe["status"] == "ok")
        & (dataframe["item_price_aed"] > 0)
        & (dataframe["extra_charges_aed"] > 0)
    ].copy()

    rejected = dataframe[
        ~dataframe.index.isin(eligible.index)
    ].copy()

    rejected["rejection_reason"] = ""

    rejected.loc[
        rejected["status"] != "ok",
        "rejection_reason",
    ] = rejected["status"]

    rejected.loc[
        (rejected["status"] == "ok")
        & (rejected["item_price_aed"] <= 0),
        "rejection_reason",
    ] = "item_price_missing"

    rejected.loc[
        (rejected["status"] == "ok")
        & (rejected["item_price_aed"] > 0)
        & (rejected["extra_charges_aed"] <= 0),
        "rejection_reason",
    ] = "shipping_import_charges_missing"

    if eligible.empty:
        print(
            "Tam maliyeti hesaplanabilen uygun teklif bulunamadı."
        )

        rejected.to_csv(
            REJECTED_FILE,
            index=False,
            encoding="utf-8-sig",
        )

        return

    best_rows = (
        eligible
        .sort_values(
            by=[
                "asin",
                "landed_cost_aed",
            ],
            ascending=[
                True,
                True,
            ],
        )
        .groupby(
            "asin",
            as_index=False,
        )
        .first()
    )

    best_rows.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    rejected.to_csv(
        REJECTED_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print("=" * 70)
    print("Gerçek landed cost karşılaştırması tamamlandı")
    print("=" * 70)
    print("Uygun ASIN:", len(best_rows))
    print("Final dosya:", OUTPUT_FILE)
    print("Elenen teklifler:", REJECTED_FILE)

    columns = [
        "asin",
        "marketplace",
        "item_price_aed",
        "extra_charges_aed",
        "landed_cost_aed",
        "charges_type",
    ]

    print(
        best_rows[columns].to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()