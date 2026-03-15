import json
import time
from datetime import date
from pathlib import Path
from slugify import slugify

DATA_DIR = Path(__file__).parent.parent / "data"
RESTAURANTS_FILE = DATA_DIR / "restaurants.json"
PROCESSED_FILE = DATA_DIR / "processed.json"
CHEFS_FILE = DATA_DIR / "chefs.json"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
GEOCODE_HEADERS = {
    "User-Agent": "chef-recs/1.0 (github.com/jcubb/chef-recs)"
}


# ─── File I/O ─────────────────────────────────────────────────────────────────

def load_restaurants() -> list[dict]:
    if not RESTAURANTS_FILE.exists():
        return []
    return json.loads(RESTAURANTS_FILE.read_text(encoding="utf-8"))


def save_restaurants(restaurants: list[dict]) -> None:
    RESTAURANTS_FILE.write_text(
        json.dumps(restaurants, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def load_processed() -> list[dict]:
    if not PROCESSED_FILE.exists():
        return []
    return json.loads(PROCESSED_FILE.read_text(encoding="utf-8"))


def save_processed(processed: list[dict]) -> None:
    PROCESSED_FILE.write_text(
        json.dumps(processed, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def get_processed_urls() -> set[str]:
    return {p["url"] for p in load_processed()}


# ─── ID generation ────────────────────────────────────────────────────────────

def make_id(name: str, neighborhood: str) -> str:
    slug_parts = name
    if neighborhood:
        slug_parts += " " + neighborhood
    return slugify(slug_parts)


# ─── Deduplication & merging ──────────────────────────────────────────────────

def _merge_into(existing: dict, new: dict) -> None:
    """Merge a new restaurant record into an existing one in-place."""
    # Merge recommended_by: deduplicate by (chef, source_url)
    existing_keys = {
        (r["chef"], r["source_url"]) for r in existing["recommended_by"]
    }
    for chef in new.get("recommended_by", []):
        key = (chef, new["source_url"])
        if key not in existing_keys:
            existing["recommended_by"].append({
                "chef": chef,
                "source_url": new["source_url"],
                "source_name": new["source_name"],
            })
            existing_keys.add(key)

    # Merge recommended_dishes (case-insensitive dedup)
    existing_dishes_lower = {d.lower() for d in existing["recommended_dishes"]}
    for dish in new.get("recommended_dishes", []):
        if dish.lower() not in existing_dishes_lower:
            existing["recommended_dishes"].append(dish)
            existing_dishes_lower.add(dish.lower())

    # Append new context if it's not already there
    if new.get("context") and new["context"] not in existing["context"]:
        existing["context"].append(new["context"])

    # Fill in missing fields
    if not existing.get("cuisine") and new.get("cuisine"):
        existing["cuisine"] = new["cuisine"]
    if not existing.get("neighborhood") and new.get("neighborhood"):
        existing["neighborhood"] = new["neighborhood"]


def upsert_restaurants(new_records: list[dict], city_filter: list[str] | None = None) -> tuple[int, int]:
    """
    Add new restaurant records to the store, merging duplicates.
    If city_filter is provided, only records whose city matches (case-insensitive) are kept.
    Returns (added, merged) counts.
    """
    # Normalize: borough names (e.g. "Brooklyn", "Queens") used as city -> "New York"
    _BOROUGH_AS_CITY = {"brooklyn", "queens", "bronx", "staten island", "manhattan"}
    for r in new_records:
        if r.get("city", "").lower() in _BOROUGH_AS_CITY:
            r["city"] = "New York"
    # Normalize: "Manhattan" used as neighborhood -> clear it (too vague)
    for r in new_records:
        if r.get("neighborhood", "").lower() == "manhattan":
            r["neighborhood"] = ""

    if city_filter:
        allowed = {c.lower() for c in city_filter}
        new_records = [r for r in new_records if r.get("city", "").lower() in allowed]

    restaurants = load_restaurants()
    index = {r["id"]: i for i, r in enumerate(restaurants)}

    added = 0
    merged = 0

    for rec in new_records:
        rid = make_id(rec["name"], rec["neighborhood"])

        if rid in index:
            _merge_into(restaurants[index[rid]], rec)
            merged += 1
        else:
            entry = {
                "id": rid,
                "name": rec["name"],
                "address": rec.get("address", ""),
                "neighborhood": rec.get("neighborhood", ""),
                "city": rec.get("city", ""),
                "cuisine": rec.get("cuisine", ""),
                "recommended_dishes": list(rec.get("recommended_dishes", [])),
                "recommended_by": [
                    {
                        "chef": chef,
                        "source_url": rec["source_url"],
                        "source_name": rec["source_name"],
                    }
                    for chef in rec.get("recommended_by", [])
                ],
                "context": [rec["context"]] if rec.get("context") else [],
                "latitude": None,
                "longitude": None,
                "added_date": date.today().isoformat(),
            }
            restaurants.append(entry)
            index[rid] = len(restaurants) - 1
            added += 1

    save_restaurants(restaurants)
    return added, merged


def mark_processed(article: dict, restaurants_extracted: int) -> None:
    processed = load_processed()
    processed.append({
        "url": article["url"],
        "title": article["title"],
        "processed_date": date.today().isoformat(),
        "source_name": article["source_name"],
        "restaurants_extracted": restaurants_extracted,
    })
    save_processed(processed)


# ─── Geocoding ────────────────────────────────────────────────────────────────

def _nominatim_query(query: str) -> tuple[float, float] | tuple[None, None]:
    import requests
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1},
            headers=GEOCODE_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        print(f"  [geocoder] Request error: {e}")
    return None, None


_TYPE_WORDS = {"steakhouse", "restaurant", "bar", "cafe", "bakery", "bistro", "grill", "tavern", "brasserie"}


def _normalize_name(name: str) -> str:
    """Normalize name for geocoding: replace & with 'and', strip accents."""
    import unicodedata
    name = name.replace("&", "and")
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return name.strip()


def _geocode_one(name: str, neighborhood: str, city: str, address: str = "") -> tuple[float, float] | tuple[None, None]:
    # Tier 1: name + neighborhood + city
    parts = [p for p in [name, neighborhood, city] if p]
    lat, lng = _nominatim_query(", ".join(parts))
    if lat is not None:
        return lat, lng

    # Tier 2: name + city only (neighborhood can confuse Nominatim)
    if neighborhood:
        time.sleep(1.1)
        lat, lng = _nominatim_query(", ".join([p for p in [name, city] if p]))
        if lat is not None:
            return lat, lng

    # Tier 3: strip generic type words (e.g. "Peter Luger Steakhouse" -> "Peter Luger")
    words = name.split()
    stripped = " ".join(w for w in words if w.lower() not in _TYPE_WORDS)
    if stripped != name and stripped:
        time.sleep(1.1)
        lat, lng = _nominatim_query(", ".join([p for p in [stripped, city] if p]))
        if lat is not None:
            return lat, lng

    # Tier 4: normalize name (& -> and, strip accents) + city
    normalized = _normalize_name(name)
    if normalized != name and normalized:
        time.sleep(1.1)
        lat, lng = _nominatim_query(", ".join([p for p in [normalized, city] if p]))
        if lat is not None:
            return lat, lng

    # Tier 5: normalize + strip type words + city
    norm_stripped = " ".join(w for w in normalized.split() if w.lower() not in _TYPE_WORDS)
    if norm_stripped and norm_stripped != normalized:
        time.sleep(1.1)
        lat, lng = _nominatim_query(", ".join([p for p in [norm_stripped, city] if p]))
        if lat is not None:
            return lat, lng

    # Tier 6: street address + city (most reliable when available)
    if address:
        time.sleep(1.1)
        lat, lng = _nominatim_query(f"{address}, {city}")
        if lat is not None:
            return lat, lng

    return None, None


def geocode_missing() -> tuple[int, list[str]]:
    """
    Geocode restaurants with null lat/lng or geocode_failed=True.
    Returns (count_geocoded, list_of_still_failed_names).
    """
    restaurants = load_restaurants()
    geocoded = 0
    failed = []

    for r in restaurants:
        if r["latitude"] is not None:
            continue

        lat, lng = _geocode_one(
            r["name"], r["neighborhood"], r["city"], r.get("address", "")
        )
        if lat is not None:
            r["latitude"] = lat
            r["longitude"] = lng
            r.pop("geocode_failed", None)
            geocoded += 1
            print(f"  [geocoder] {r['name']} -> ({lat:.4f}, {lng:.4f})")
        else:
            r["geocode_failed"] = True
            failed.append(r["name"])
            print(f"  [geocoder] No result for '{r['name']}'")

        time.sleep(1.1)  # Nominatim requires max 1 req/sec

    if geocoded or failed:
        save_restaurants(restaurants)

    return geocoded, failed


# ─── Chefs ────────────────────────────────────────────────────────────────────

def load_chefs() -> list[dict]:
    if not CHEFS_FILE.exists():
        return []
    return json.loads(CHEFS_FILE.read_text(encoding="utf-8"))


def save_chefs(chefs: list[dict]) -> None:
    CHEFS_FILE.write_text(
        json.dumps(chefs, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def upsert_chef(article: dict, chef_info: dict) -> bool:
    """
    Add a chef entry if not already present (keyed by article URL).
    Returns True if a new entry was added.
    """
    chefs = load_chefs()
    if any(c["article_url"] == article["url"] for c in chefs):
        return False

    chefs.append({
        "id": slugify(chef_info["name"]) if chef_info.get("name") else slugify(article["url"]),
        "name": chef_info.get("name", ""),
        "restaurant": chef_info.get("restaurant", ""),
        "city": chef_info.get("city", ""),
        "article_url": article["url"],
        "article_title": article["title"],
        "article_date": article.get("date", ""),
        "source_name": article["source_name"],
    })
    save_chefs(chefs)
    return True
