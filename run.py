"""
Usage:
  python run.py                # full pipeline: scrape → extract → geocode → build site
  python run.py --scrape-only  # scrape and extract only, skip site rebuild
  python run.py --build-only   # rebuild site from existing data, skip scraping
  python run.py --status       # show stats: total restaurants, sources, last update
"""

import sys
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def load_sources() -> list[dict]:
    sources_file = Path(__file__).parent / "sources.json"
    return json.loads(sources_file.read_text(encoding="utf-8"))


def run_pipeline(scrape: bool = True, build: bool = True) -> None:
    from openai import OpenAI
    from src.scraper import scrape_new_articles
    from src.extractor import extract_restaurants, extract_chef_info
    from src.store import (
        get_processed_urls,
        upsert_restaurants,
        mark_processed,
        geocode_missing,
        upsert_chef,
    )
    from src.site_generator import build_site

    if scrape:
        sources = load_sources()
        processed_urls = get_processed_urls()

        # Build city filter map: source name -> list of allowed cities
        source_city_filters = {s["name"]: s.get("city_filter") for s in sources}

        print(f"\n[run] Starting scrape ({len(sources)} source(s))...")
        articles = scrape_new_articles(sources, processed_urls)

        if not articles:
            print("[run] No new articles found.")
        else:
            print(f"[run] Found {len(articles)} new article(s). Extracting restaurants...")
            client = OpenAI()

            for article in articles:
                print(f"\n[run] Extracting: {article['title']}")

                # Extract chef info
                try:
                    chef_info = extract_chef_info(article, client)
                    if chef_info:
                        added_chef = upsert_chef(article, chef_info)
                        if added_chef:
                            print(f"  [run] Chef: {chef_info['name']} of {chef_info.get('restaurant', '?')}")
                except Exception as e:
                    print(f"  [run] Chef extraction failed: {e}")

                try:
                    restaurants = extract_restaurants(article, client)
                except Exception as e:
                    print(f"  [run] Extraction failed: {e}")
                    restaurants = []

                city_filter = source_city_filters.get(article["source_name"])
                added, merged = upsert_restaurants(restaurants, city_filter=city_filter)
                mark_processed(article, len(restaurants))
                print(f"  [run] {len(restaurants)} extracted -> {added} added, {merged} merged")

        print("\n[run] Geocoding missing coordinates...")
        geocoded, geo_failed = geocode_missing()
        print(f"[run] Geocoded {geocoded} restaurant(s).")
        if geo_failed:
            print(f"\n  *** {len(geo_failed)} restaurant(s) could not be geocoded (will retry next run):")
            for name in geo_failed:
                print(f"      - {name}")
            print("  *** Consider adding a street address to fix these.\n")

    if build:
        print("\n[run] Building site...")
        build_site()

    print("\n[run] Done.")


def show_status() -> None:
    from src.store import load_restaurants, load_processed

    restaurants = load_restaurants()
    processed = load_processed()

    sep = "-" * 40
    print(f"\n{sep}")
    print(f"  Total restaurants : {len(restaurants)}")
    print(f"  Articles processed: {len(processed)}")

    if processed:
        last = max(processed, key=lambda p: p["processed_date"])
        print(f"  Last processed   : {last['processed_date']} - \"{last['title']}\"")

    sources = {}
    for r in restaurants:
        for rb in r.get("recommended_by", []):
            sn = rb.get("source_name", "Unknown")
            sources[sn] = sources.get(sn, 0) + 1

    if sources:
        print(f"\n  By source:")
        for src, count in sorted(sources.items()):
            print(f"    {src}: {count} recommendations")

    geocoded = sum(1 for r in restaurants if r["latitude"] is not None)
    print(f"\n  Geocoded: {geocoded}/{len(restaurants)}")
    failed = [r["name"] for r in restaurants if r.get("geocode_failed")]
    if failed:
        print(f"  Geocode failures ({len(failed)}):")
        for name in failed:
            print(f"    - {name}")
    print(f"{sep}\n")


def main() -> None:
    args = sys.argv[1:]

    if "--status" in args:
        show_status()
    elif "--scrape-only" in args:
        run_pipeline(scrape=True, build=False)
    elif "--build-only" in args:
        run_pipeline(scrape=False, build=True)
    else:
        run_pipeline(scrape=True, build=True)


if __name__ == "__main__":
    main()
