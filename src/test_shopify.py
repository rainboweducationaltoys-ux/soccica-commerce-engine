from shopify_api import test_connection


def main() -> None:
    shop = test_connection()

    print("=" * 50)
    print("Shopify bağlantısı başarılı")
    print("=" * 50)
    print("Mağaza adı:", shop["name"])
    print("Domain:", shop["domain"])


if __name__ == "__main__":
    main()