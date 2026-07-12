import json
import os
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv()


OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY",
    "",
).strip()

AI_REWRITE_ENABLED = (
    os.getenv(
        "AI_REWRITE_ENABLED",
        "false",
    )
    .strip()
    .lower()
    == "true"
)

OPENAI_MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5-mini",
).strip()


def build_fallback_result(
    title: str,
    bullets: list[str],
    description: str,
    brand: str,
) -> dict[str, Any]:
    return {
        "title": title,
        "bullets": bullets,
        "description": description,
        "seo_title": title[:70],
        "meta_description": (
            description[:155]
            if description
            else title[:155]
        ),
        "product_type": "",
        "tags": [
            brand
        ] if brand else [],
    }


def validate_ai_settings() -> None:
    if not OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY eksik."
        )


def rewrite_product_content(
    title: str,
    bullets: list[str],
    description: str,
    brand: str,
    asin: str,
) -> dict[str, Any]:
    fallback = build_fallback_result(
        title=title,
        bullets=bullets,
        description=description,
        brand=brand,
    )

    if not AI_REWRITE_ENABLED:
        return fallback

    validate_ai_settings()

    prompt = {
        "task": (
            "Rewrite this product for a premium Shopify store "
            "in clear English."
        ),
        "requirements": [
            "Do not invent specifications.",
            "Do not mention Amazon.",
            "Do not mention ratings or reviews.",
            "Keep the title under 140 characters.",
            "Create exactly 5 concise bullet points.",
            "Create a professional product description.",
            "Create an SEO title under 70 characters.",
            "Create a meta description under 155 characters.",
            "Return valid JSON only.",
        ],
        "product": {
            "asin": asin,
            "brand": brand,
            "title": title,
            "bullets": bullets,
            "description": description,
        },
        "output_schema": {
            "title": "string",
            "bullets": ["string"],
            "description": "string",
            "seo_title": "string",
            "meta_description": "string",
            "product_type": "string",
            "tags": ["string"],
        },
    }

    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization":
                f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_MODEL,
            "input": json.dumps(
                prompt,
                ensure_ascii=False,
            ),
        },
        timeout=120,
    )

    if not response.ok:
        raise RuntimeError(
            "AI rewrite hatası: "
            f"{response.status_code} - "
            f"{response.text}"
        )

    payload = response.json()

    output_text = payload.get(
        "output_text",
        "",
    )

    if not output_text:
        return fallback

    try:
        result = json.loads(output_text)
    except json.JSONDecodeError:
        return fallback

    return {
        "title": str(
            result.get(
                "title",
                fallback["title"],
            )
        ).strip(),
        "bullets": (
            result.get("bullets")
            if isinstance(
                result.get("bullets"),
                list,
            )
            else fallback["bullets"]
        ),
        "description": str(
            result.get(
                "description",
                fallback["description"],
            )
        ).strip(),
        "seo_title": str(
            result.get(
                "seo_title",
                fallback["seo_title"],
            )
        ).strip()[:70],
        "meta_description": str(
            result.get(
                "meta_description",
                fallback[
                    "meta_description"
                ],
            )
        ).strip()[:155],
        "product_type": str(
            result.get(
                "product_type",
                "",
            )
        ).strip(),
        "tags": (
            result.get("tags")
            if isinstance(
                result.get("tags"),
                list,
            )
            else fallback["tags"]
        ),
    }