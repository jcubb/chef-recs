import json
import re
from openai import OpenAI, APIError

MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """You are a restaurant data extraction assistant.
Given the text of a food newsletter article, extract every restaurant that is being recommended.

Rules:
- Only extract restaurants that are being RECOMMENDED (not the chef's own restaurant, unless another chef also recommends it)
- If a neighborhood is mentioned, include it; otherwise use an empty string
- For Manhattan restaurants, always use the specific neighborhood (e.g. "West Village", "SoHo", "Flatiron", "Lower East Side") — never use "Manhattan" as a neighborhood value. If the specific neighborhood is unknown, use an empty string.
- City should reflect where the restaurant is located — most will be in New York but some articles may cover other cities
- For New York restaurants, city should always be "New York" regardless of which borough or neighborhood — never use a borough name (Brooklyn, Queens, etc.) or neighborhood name as the city
- Extract specific dish recommendations if any are mentioned; otherwise use an empty list
- Note which chef(s) or person(s) recommended each restaurant
- Provide a brief (1-2 sentence) context for why it was recommended
- If no restaurants are mentioned or the article is not about restaurant recommendations, return an empty list

Return ONLY a JSON array. No explanation, no markdown, just the raw JSON array."""

USER_PROMPT_TEMPLATE = """Article source: {source_name}
Article URL: {url}
Article title: {title}

Article text:
{text}

Extract all restaurant recommendations as a JSON array. Each object must have these exact keys:
- name (string)
- neighborhood (string, empty string if unknown)
- city (string)
- cuisine (string, empty string if unknown)
- recommended_dishes (array of strings)
- recommended_by (array of strings — chef/person names)
- context (string — brief description of why it was recommended)
- source_url (string — the article URL)
- source_name (string — the newsletter name)"""


def extract_restaurants(article: dict, client: OpenAI) -> list[dict]:
    """
    Send an article to the OpenAI API and return extracted restaurant records.
    Returns an empty list if extraction fails or no restaurants are found.
    """
    prompt = USER_PROMPT_TEMPLATE.format(
        source_name=article["source_name"],
        url=article["url"],
        title=article["title"],
        text=article["text"][:12000],  # cap at ~12k chars to stay within token limits
    )

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
    except APIError as e:
        print(f"  [extractor] API error for '{article['title']}': {e}")
        return []

    raw = response.choices[0].message.content.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [extractor] JSON parse error for '{article['title']}': {e}")
        print(f"  [extractor] Raw response: {raw[:500]}")
        return []

    # response_format=json_object may wrap the array in a key
    if isinstance(parsed, dict):
        restaurants = next(
            (v for v in parsed.values() if isinstance(v, list)), []
        )
    elif isinstance(parsed, list):
        restaurants = parsed
    else:
        print(f"  [extractor] Unexpected response type for '{article['title']}'")
        return []

    # Ensure all required fields are present with sensible defaults
    cleaned = []
    for r in restaurants:
        if not isinstance(r, dict) or not r.get("name"):
            continue
        cleaned.append({
            "name": r.get("name", "").strip(),
            "neighborhood": r.get("neighborhood", "").strip(),
            "city": r.get("city", "").strip(),
            "cuisine": r.get("cuisine", "").strip(),
            "recommended_dishes": [d for d in r.get("recommended_dishes", []) if d],
            "recommended_by": [p for p in r.get("recommended_by", []) if p],
            "context": r.get("context", "").strip(),
            "source_url": r.get("source_url", article["url"]),
            "source_name": r.get("source_name", article["source_name"]),
        })

    return cleaned


CHEF_SYSTEM_PROMPT = """You are extracting information about the featured chef from a food newsletter article.
Return a JSON object with exactly these fields:
- name: the full name of the featured chef (string, without title like "Chef")
- restaurant: the name of the chef's own restaurant or primary restaurant (string, empty string if not mentioned)
- city: the city where the chef primarily works (string)
Return ONLY a JSON object. No explanation, no markdown, just raw JSON."""

CHEF_USER_TEMPLATE = """Article title: {title}

Article text (first 3000 chars):
{text}

Extract the featured chef's name, their restaurant, and city as a JSON object."""


def extract_chef_info(article: dict, client: OpenAI) -> dict | None:
    """
    Extract the featured chef's name, restaurant, and city from an article.
    Returns a dict or None if extraction fails.
    """
    prompt = CHEF_USER_TEMPLATE.format(
        title=article["title"],
        text=article["text"][:3000],
    )

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": CHEF_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=256,
            response_format={"type": "json_object"},
        )
    except APIError as e:
        print(f"  [extractor] Chef extraction API error: {e}")
        return None

    raw = response.choices[0].message.content.strip()
    try:
        info = json.loads(raw)
        if isinstance(info, dict) and info.get("name"):
            return {
                "name": info.get("name", "").strip(),
                "restaurant": info.get("restaurant", "").strip(),
                "city": info.get("city", "").strip(),
            }
    except json.JSONDecodeError:
        pass

    return None
