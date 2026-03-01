"""
AI Product Classifier – assigns a category to a product using the configured LLM.
Runs when a seller creates a new product; output is strictly JSON: {"category": "category_name"}.
"""
import json
import logging
import re

import requests

from django.conf import settings

from ai_assistant.services import OPENAI_API_URL, get_api_key

logger = logging.getLogger(__name__)

# Allowed categories (must match Products.PRODUCT_CATEGORY_CHOICES)
VALID_CATEGORIES = frozenset({
    "beauty_and_skincare", "electronics_and_gadgets", "fragrances",
    "fashion_and_apparel", "health_and_supplements", "home_and_kitchen", "general_retail",
})

# Keywords in LLM category string → canonical category (substring match, lowercased)
CATEGORY_KEYWORD_FALLBACK = [
    ("supplement", "health_and_supplements"),
    ("vitamin", "health_and_supplements"),
    ("dietary", "health_and_supplements"),
    ("nutritional", "health_and_supplements"),
    ("nutrition", "health_and_supplements"),
    ("health", "health_and_supplements"),
]

CLASSIFIER_SYSTEM_PROMPT = """You are a highly precise automated product classifier for an e-commerce platform. Your ONLY task is to analyze the provided product title and description and map it to EXACTLY ONE of the allowed categories.

CRITICAL INSTRUCTIONS:
1. You must output ONLY a raw, valid JSON object.
2. DO NOT wrap the output in Markdown code blocks (e.g., no ```json ... ```).
3. DO NOT output any introductory or concluding text. No explanations.
4. The input text may be in Arabic, French, English, or local dialects (like Moroccan Darija). Understand the context regardless of the language.

ALLOWED CATEGORIES AND RULES:
- "beauty_and_skincare": Cosmetics, skincare, makeup, hair care, grooming tools (even if electric like hair straighteners).
- "electronics_and_gadgets": Tech devices, computers, phones, smart home tech, tech accessories. (If a product is a beauty or health device, classify it as beauty or health, not electronics).
- "fragrances": Perfumes, colognes, oud, body mists, luxury scents.
- "fashion_and_apparel": Clothing, shoes, bags, wearable accessories, jewelry.
- "health_and_supplements": Vitamins, dietary supplements, nutritional supplements, protein/omega/minerals, pain relief creams (e.g., joint creams), natural remedies, medical braces, herbal products, probiotics. Any supplement or health-related product MUST use this category.
- "home_and_kitchen": Home appliances, furniture, home decor, kitchenware, cleaning supplies.
- "general_retail": Use this ONLY if the product strictly does not fit any of the above (e.g., car parts, toys, pet supplies).

EXPECTED OUTPUT FORMAT:
{"category": "one_of_the_allowed_categories_exactly_as_written"}
"""

def classify_product(title, description):
    """
    Call the LLM to classify the product into one of: beauty, electronics, fragrances, general.
    Returns the category string. On any error or invalid response, returns DEFAULT_CATEGORY.
    """
    api_key = get_api_key()
    if not api_key:
        logger.warning("classify_product: no API key; returning default category")
        return "general_retail"

    title = (title or "").strip() or "Product"
    description = (description or "").strip() or ""
    user_content = f"Title: {title}\nDescription: {description}"

    payload = {
        "model": getattr(settings, "OPENAI_PRODUCT_CLASSIFIER_MODEL", "gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": 50,
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=15)
        print(response.json())
        if response.status_code != 200:
            logger.warning("classify_product: API status %s, body %s", response.status_code, response.text[:200])
            return "general_retail"

        data = response.json()
        choice = data.get("choices", [{}])[0]
        content = (choice.get("message", {}).get("content") or "").strip()
        if not content:
            return "general_retail"

        # Strip markdown code blocks if present
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```\s*$", "", content).strip()

        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            return "general_retail"
        category = (parsed.get("category") or "").strip().lower()
        if category in VALID_CATEGORIES:
            return category
        # Map common typos/variants to canonical category (exact match)
        CATEGORY_ALIASES = {
            "beauty_and_skincare": (
                "beauty", "cosmetics", "skincare", "makeup", "hair care",
                "grooming tools", "hair straighteners",
            ),
            "electronics_and_gadgets": (
                "electronics", "tech", "technology", "computers", "phones",
                "smart home tech", "tech accessories",
            ),
            "fragrances": (
                "perfume", "fragrance", "oud", "body mists", "luxury scents",
            ),
            "fashion_and_apparel": (
                "fashion", "apparel", "clothing", "shoes", "bags", "accessories",
                "jewelry", "wearable accessories",
            ),
            "health_and_supplements": (
                "health", "supplements", "supplement", "vitamins", "vitamin",
                "natural remedies", "medical braces", "pain relief creams", "joint creams",
                "dietary supplements", "nutritional supplements", "health supplements",
                "nutrition", "protein", "omega", "minerals", "herbal", "probiotics",
            ),
            "home_and_kitchen": (
                "home", "kitchen", "appliances", "furniture", "home decor",
                "kitchenware", "cleaning supplies",
            ),
        }
        for canonical, aliases in CATEGORY_ALIASES.items():
            if category in aliases:
                return canonical
        # Keyword fallback: LLM sometimes returns phrases like "dietary supplements"
        for keyword, canonical in CATEGORY_KEYWORD_FALLBACK:
            if keyword in category and canonical in VALID_CATEGORIES:
                return canonical
        # Last resort: if title/description clearly indicate supplement, use health_and_supplements
        combined = f"{title} {description}".lower()
        if any(
            w in combined
            for w in ("supplement", "supplements", "vitamin", "vitamins", "nutritional", "dietary", "probiotic", "omega", "mineral")
        ):
            return "health_and_supplements"
        return "general_retail"

    except json.JSONDecodeError as e:
        logger.warning("classify_product: JSON decode error %s for content %s", e, content[:100] if content else "")
        return "general_retail"
    except (requests.RequestException, KeyError, IndexError, TypeError) as e:
        logger.warning("classify_product: error %s", e, exc_info=True)
        return "general_retail"
