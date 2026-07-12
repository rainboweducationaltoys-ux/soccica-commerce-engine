from shopify_api import create_draft_product


def main() -> None:
    product = create_draft_product(
        title="Soccica API Test Product",
        description_html=(
            "<h2>Test Product</h2>"
            "<p>This product was created through "
            "the Soccica Shopify API tool.</p>"
        ),
        vendor="Soccica",
        product_type="Toys",
        tags=[
            "API Test",
            "Soccica",
        ],
        image_urls=[],
    )

    print("=" * 50)
    print("Taslak ürün oluşturuldu")
    print("=" * 50)
    print("ID:", product["id"])
    print("Başlık:", product["title"])
    print("Handle:", product["handle"])
    print("Durum:", product["status"])


if __name__ == "__main__":
    main()