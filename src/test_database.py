from database import (
    add_asins,
    get_status_summary,
    initialize_database,
)


def main() -> None:
    initialize_database()

    inserted = add_asins(
        [
            "B00TFWOS8Y",
            "B0084JUNXS",
            "B06WWFWGNX",
            "B0084JUNXS",
        ]
    )

    print("Yeni eklenen:", inserted)
    print("Durum:", get_status_summary())


if __name__ == "__main__":
    main()