import re
from typing import Any


CATEGORY_RULES = {
    "Arts & Crafts": [
        "art",
        "craft",
        "drawing",
        "painting",
        "coloring",
        "crayon",
        "pencil",
        "marker",
        "scrapbook",
        "tracing",
    ],
    "Building Toys": [
        "building",
        "blocks",
        "brick",
        "construction set",
        "magnetic tiles",
        "magnetic blocks",
    ],
    "Puzzles": [
        "puzzle",
        "jigsaw",
        "brain teaser",
    ],
    "Educational Toys": [
        "educational",
        "learning",
        "alphabet",
        "math",
        "science",
        "stem",
        "montessori",
    ],
    "Outdoor Toys": [
        "outdoor",
        "garden",
        "sports",
        "ball",
        "scooter",
        "water toy",
    ],
    "Games": [
        "game",
        "board game",
        "card game",
        "family game",
    ],
    "Baby & Toddler": [
        "baby",
        "toddler",
        "sippy",
        "bottle",
        "teether",
        "0 months",
        "6 months",
        "12 months",
    ],
    "Jewelry": [
        "necklace",
        "earrings",
        "bracelet",
        "ring",
        "sterling silver",
        "jewelry",
    ],
    "Home & Living": [
        "bedding",
        "duvet",
        "sheet",
        "bath mat",
        "napkin holder",
        "home decor",
    ],
    "Tools & Hardware": [
        "wrench",
        "tool",
        "drill",
        "cutter",
        "blade",
        "lock",
        "cylinder",
        "connector",
    ],
    "Fashion": [
        "shirt",
        "t-shirt",
        "bra",
        "tights",
        "pants",
        "shorts",
        "underwear",
        "dress",
    ],
}


AGE_PATTERNS = [
    (
        "Age 0–2",
        [
            r"\b0\+?\s*months?\b",
            r"\b6\+?\s*months?\b",
            r"\b12\+?\s*months?\b",
            r"\bbaby\b",
        ],
    ),
    (
        "Age 3–5",
        [
            r"\bage[s]?\s*3\b",
            r"\bage[s]?\s*4\b",
            r"\bage[s]?\s*5\b",
            r"\b3\+\b",
            r"\b4\+\b",
            r"\b5\+\b",
        ],
    ),
    (
        "Age 6–8",
        [
            r"\bage[s]?\s*6\b",
            r"\bage[s]?\s*7\b",
            r"\bage[s]?\s*8\b",
            r"\b6\+\b",
            r"\b7\+\b",
            r"\b8\+\b",
        ],
    ),
    (
        "Age 9+",
        [
            r"\bage[s]?\s*9\b",
            r"\bage[s]?\s*10\b",
            r"\bage[s]?\s*11\b",
            r"\bage[s]?\s*12\b",
            r"\b9\+\b",
            r"\b10\+\b",
        ],
    ),
]


def safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def normalize_tag(value: str) -> str:
    return " ".join(
        safe_text(value).split()
    )[:255]


def detect_categories(
    title: str,
    bullets: list[str],
    description: str,
    product_type: str = "",
) -> list[str]:
    combined_text = " ".join(
        [
            title,
            " ".join(bullets),
            description,
            product_type,
        ]
    ).lower()

    categories: list[str] = []

    for category, keywords in CATEGORY_RULES.items():
        if any(
            keyword in combined_text
            for keyword in keywords
        ):
            categories.append(category)

    return categories


def detect_age_tags(
    title: str,
    bullets: list[str],
    description: str,
) -> list[str]:
    combined_text = " ".join(
        [
            title,
            " ".join(bullets),
            description,
        ]
    ).lower()

    age_tags: list[str] = []

    for age_tag, patterns in AGE_PATTERNS:
        if any(
            re.search(
                pattern,
                combined_text,
                re.IGNORECASE,
            )
            for pattern in patterns
        ):
            age_tags.append(age_tag)

    return age_tags


def get_price_collection(
    shopify_price_aed: float,
) -> str:
    if shopify_price_aed < 100:
        return "Price: Under 100 AED"

    if shopify_price_aed < 200:
        return "Price: 100–199 AED"

    if shopify_price_aed < 300:
        return "Price: 200–299 AED"

    if shopify_price_aed < 500:
        return "Price: 300–499 AED"

    return "Price: 500+ AED"


def get_marketplace_tag(
    marketplace: str,
) -> str:
    marketplace_upper = safe_text(
        marketplace
    ).upper()

    mapping = {
        "US": "Imported from Amazon US",
        "UK": "Imported from Amazon UK",
        "DE": "Imported from Amazon Germany",
        "FR": "Imported from Amazon France",
        "IT": "Imported from Amazon Italy",
        "ES": "Imported from Amazon Spain",
    }

    for code, tag in mapping.items():
        if (
            marketplace_upper == code
            or code in marketplace_upper
        ):
            return tag

    return "Global Import"


COLLECTION_EXCLUDED_PREFIXES = (
    "AI:",
    "ASIN:",
    "Product Type:",
)


def is_collection_worthy_tag(tag: str) -> bool:
    text = safe_text(tag)

    if not text:
        return False

    return not text.startswith(
        COLLECTION_EXCLUDED_PREFIXES
    )


def build_collection_tags(
    title: str,
    bullets: list[str],
    description: str,
    brand: str,
    product_type: str,
    marketplace: str,
    shopify_price_aed: float,
    ai_tags: list[str] | None = None,
) -> list[str]:
    tags: list[str] = [
        "Global Import",
        get_marketplace_tag(
            marketplace
        ),
        get_price_collection(
            shopify_price_aed
        ),
    ]

    if brand:
        clean_brand = (
            brand
            .replace("Visit the ", "")
            .replace(" Store", "")
            .replace("Brand:", "")
            .strip()
        )

        if clean_brand:
            tags.append(
                f"Brand: {clean_brand}"
            )

    if product_type:
        tags.append(
            f"Product Type: {product_type}"
        )

    categories = detect_categories(
        title=title,
        bullets=bullets,
        description=description,
        product_type=product_type,
    )

    for category in categories:
        tags.append(
            f"Category: {category}"
        )

    age_tags = detect_age_tags(
        title=title,
        bullets=bullets,
        description=description,
    )

    tags.extend(age_tags)

    for ai_tag in ai_tags or []:
        if safe_text(ai_tag):
            tags.append(
                f"AI: {safe_text(ai_tag)}"
            )

    cleaned_tags: list[str] = []
    seen: set[str] = set()

    for tag in tags:
        normalized = normalize_tag(tag)

        if (
            normalized
            and normalized.lower() not in seen
        ):
            cleaned_tags.append(
                normalized
            )
            seen.add(
                normalized.lower()
            )

    return cleaned_tags