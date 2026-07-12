import re

from playwright.sync_api import Page


def get_text(page, selector):
    try:
        locator = page.locator(selector).first

        if locator.count() == 0:
            return ""

        return locator.inner_text(timeout=10000).strip()

    except Exception:
        return ""


def get_asin(url):
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)

    if match:
        return match.group(1)

    return ""


def get_price(page):
    selectors = [
        "span.a-price span.a-offscreen",
        ".a-price .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-offscreen",
        "#price_inside_buybox",
    ]

    for selector in selectors:
        price = get_text(page, selector)

        if price:
            return price

    return ""


def get_brand(page):
    return get_text(page, "#bylineInfo")


def get_title(page):
    return get_text(page, "#productTitle")


def get_description(page):

    description = get_text(page, "#productDescription")

    if description:
        return description

    return get_text(page, "#aplus")


def get_bullets(page):

    bullets = []

    try:

        items = page.locator(
            "#feature-bullets ul li span.a-list-item"
        )

        for i in range(items.count()):

            text = items.nth(i).inner_text().strip()

            if text:
                bullets.append(text)

    except Exception:
        pass

    return bullets


def get_images(page: Page) -> list[str]:
    images: list[str] = []

    def normalize_url(url: str) -> str:
        if not url:
            return ""

        # Amazon thumbnail boyut eklerini kaldırır.
        return re.sub(r"\._[^.]+_\.", ".", url)

    def add_url(url: str) -> None:
        url = normalize_url(url)

        if (
            url
            and url.startswith("http")
            and url not in images
        ):
            images.append(url)

    # 1. Ana görselin yüksek çözünürlüklü kaynakları
    try:
        main_image = page.locator("#landingImage").first

        if main_image.count() > 0:
            dynamic_images = main_image.get_attribute(
                "data-a-dynamic-image"
            )

            if dynamic_images:
                import json

                image_map = json.loads(dynamic_images)

                for image_url in image_map.keys():
                    add_url(image_url)

            add_url(
                main_image.get_attribute("data-old-hires") or ""
            )

            add_url(
                main_image.get_attribute("src") or ""
            )

    except Exception:
        pass

    # 2. Sayfa içindeki Amazon görsel verilerini tara
    try:
        page_content = page.content()

        patterns = [
            r'"hiRes":"(https:[^"]+)"',
            r'"large":"(https:[^"]+)"',
            r'"mainUrl":"(https:[^"]+)"',
        ]

        for pattern in patterns:
            for match in re.findall(pattern, page_content):
                image_url = (
                    match
                    .replace("\\u0026", "&")
                    .replace("\\/", "/")
                )

                add_url(image_url)

    except Exception:
        pass

    # 3. Thumbnail’lara tıklayıp değişen büyük görseli al
    try:
        thumbnails = page.locator(
            "#altImages li.imageThumbnail, "
            "#altImages li.item, "
            "#imageBlockThumbs li"
        )

        for index in range(thumbnails.count()):
            thumbnail = thumbnails.nth(index)

            try:
                thumbnail.scroll_into_view_if_needed()
                thumbnail.click(timeout=5000)
                page.wait_for_timeout(700)

                main_image = page.locator("#landingImage").first

                add_url(
                    main_image.get_attribute("data-old-hires") or ""
                )

                add_url(
                    main_image.get_attribute("src") or ""
                )

            except Exception:
                continue

    except Exception:
        pass

    # Çok fazla alakasız Amazon görseli gelmesini engeller.
    return images[:12]