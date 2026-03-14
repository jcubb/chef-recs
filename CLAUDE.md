# chef-recs

## Project Overview

A tool that scrapes restaurant recommendations from food-focused Substack newsletters (starting with [Eating with Experts](https://eatingwithexperts.substack.com)), extracts structured restaurant data using the OpenAI API, stores it in a local JSON database, and generates a static site with list, map, and chef views — hosted for free via GitHub Pages.

**Repo:** `github.com/jcubb/chef-recs`
**Live site:** `jcubb.github.io/chef-recs`

## Architecture

```
Substack newsletters
        │
        ▼
   Scraper (requests + BeautifulSoup)
   - Fetches archive page, finds article URLs
   - Filters by url_pattern (e.g. "where-")
   - Skips already-processed articles
   - Extracts article date from <time> tag
        │
        ▼
   Extractor (OpenAI gpt-4o-mini)
   - Sends article text to OpenAI API
   - Extracts restaurant list as JSON
   - Extracts featured chef name + restaurant + city
        │
        ▼
   Data Store (JSON files)
   - data/restaurants.json — the restaurant collection
   - data/processed.json  — list of already-processed article URLs
   - data/chefs.json       — featured chefs with their own restaurant info
   - Deduplication by restaurant name + neighborhood
   - City filtering: only stores restaurants in allowed cities
        │
        ▼
   Site Generator
   - Builds docs/index.html from restaurant + chef data
   - List view + Leaflet.js map with pins + Chefs reference page
   - Filterable by neighborhood, cuisine, recommending chef, source
        │
        ▼
   GitHub Pages (serves from /docs)
```

## User Workflow

```bash
python run.py              # scrape new articles, extract restaurants, rebuild site
git add -A && git commit -m "update restaurants" && git push
```

That's it. The site updates on push via GitHub Pages.

## Directory Structure

```
chef-recs/
├── CLAUDE.md              # this file
├── README.md              # public-facing project description
├── run.py                 # CLI entry point — runs full pipeline
├── requirements.txt       # Python dependencies
├── .env                   # OPENAI_API_KEY (gitignored)
├── .gitignore
├── src/
│   ├── __init__.py
│   ├── scraper.py         # Substack fetching logic
│   ├── extractor.py       # OpenAI extraction logic
│   ├── store.py           # JSON read/write, dedup, geocoding, chef storage
│   └── site_generator.py  # builds static HTML into docs/
├── data/
│   ├── restaurants.json   # restaurant records
│   ├── processed.json     # tracked article URLs + processing timestamps
│   └── chefs.json         # featured chefs + their own restaurants
├── docs/                  # GitHub Pages source
│   └── index.html         # generated static site (list + map + chefs)
└── sources.json           # configured Substack sources
```

## Component Details

### 1. Source Configuration (`sources.json`)

```json
[
  {
    "name": "Eating with Experts",
    "archive_url": "https://eatingwithexperts.substack.com/archive",
    "enabled": true,
    "url_pattern": "where-",
    "city_filter": ["New York", "New York City", "NYC", "Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"]
  }
]
```

- `url_pattern`: if set, only article URLs containing this string are processed. Used to skip non-recommendation posts (e.g. "what I ate this week").
- `city_filter`: if set, restaurants extracted from this source are only stored if their `city` field matches one of these values (case-insensitive). Covers all NYC boroughs — the extractor may label Brooklyn restaurants as "Brooklyn" or "New York" so all variants are listed.

### 2. Scraper (`src/scraper.py`)

- Fetches the Substack archive page for each enabled source
- Filters article URLs by `url_pattern` after fetching the archive
- Compares against `data/processed.json` to skip already-processed articles
- For each new article, fetches full article page and extracts:
  - Title (from `<h1>`)
  - Body text (from `div.available-content` → `article` → `div.post-content` → `div.body`)
  - Publish date (from `<time datetime="...">` tag, stored as YYYY-MM-DD)
- Returns `{url, title, text, date, source_name}` dicts

**Important notes on Substack scraping:**
- Substack paginate archive pages — handled with offset parameter
- Rate limit: 1.5 second delay between requests
- Some posts are paywalled or truncated — skipped gracefully if content < 200 chars

### 3. Extractor (`src/extractor.py`)

Uses **OpenAI gpt-4o-mini** (not Anthropic/Claude). Set `OPENAI_API_KEY` in `.env`.

Two extraction functions per article:

**`extract_restaurants(article, client)`** — extracts all recommended restaurants as a JSON array. Each object has: `name`, `neighborhood`, `city`, `cuisine`, `recommended_dishes`, `recommended_by`, `context`, `source_url`, `source_name`.

**`extract_chef_info(article, client)`** — extracts the featured chef's name, their own restaurant, and city. Returns `{name, restaurant, city}` or `None`.

The `response_format: json_object` mode may wrap the array in a key — the extractor handles this by searching for the first list value in the response dict.

### 4. Data Store (`src/store.py`)

**`data/restaurants.json`** — array of restaurant objects:
```json
[
  {
    "id": "thai-diner-nolita",
    "name": "Thai Diner",
    "neighborhood": "Nolita",
    "city": "New York",
    "cuisine": "Thai-American",
    "recommended_dishes": ["crab fried rice"],
    "recommended_by": [
      {
        "chef": "Chef Ben Selman",
        "source_url": "https://...",
        "source_name": "Eating with Experts"
      }
    ],
    "context": ["Ben's go-to spot for dining out"],
    "latitude": null,
    "longitude": null,
    "added_date": "2026-03-14"
  }
]
```

**`data/chefs.json`** — array of featured chef objects:
```json
[
  {
    "id": "alexia-duchene",
    "name": "Alexia Duchene",
    "restaurant": "Ernst",
    "city": "New York",
    "article_url": "https://...",
    "article_title": "Where Chef Alexia Duchene Eats in NYC",
    "article_date": "2024-01-15",
    "source_name": "Eating with Experts"
  }
]
```

**Deduplication logic:**
- Restaurant ID = slugify(`name + neighborhood`)
- When duplicate found: merge `recommended_by` (deduplicated by chef+url), `recommended_dishes` (case-insensitive dedup), `context`
- City filter is applied in `upsert_restaurants(records, city_filter=...)` before dedup

**`data/processed.json`** — tracks what's been scraped:
```json
[
  {
    "url": "https://eatingwithexperts.substack.com/p/where-chefs-eat-in-nyc",
    "title": "Where Chefs Eat in NYC",
    "processed_date": "2026-03-14",
    "source_name": "Eating with Experts",
    "restaurants_extracted": 5
  }
]
```

### 5. Geocoding

After extraction, `geocode_missing()` geocodes restaurants with `latitude: null` using Nominatim (OpenStreetMap). Three-tier fallback:
1. `name + neighborhood + city`
2. `name + city` (neighborhood can confuse Nominatim)
3. Stripped name + city (removes generic words like "steakhouse", "restaurant", "bar" from the name)

Rate limit: 1.1 second delay between requests (Nominatim requires max 1 req/sec).

If all 3 queries fail, lat/lng stays null — restaurant appears in list but not on map.

### 6. Site Generator (`src/site_generator.py`)

Reads `data/restaurants.json` and `data/chefs.json`, generates `docs/index.html`.

Three views:
- **List**: filterable card grid (neighborhood, cuisine, chef, source) with search
- **Map**: Leaflet.js dark-theme map (CartoDB tiles), pins for geocoded restaurants
- **Chefs**: reference page showing each featured chef's name, restaurant, and link to their article

### 7. CLI Entry Point (`run.py`)

```bash
python run.py              # full pipeline: scrape -> extract -> geocode -> build site
python run.py --scrape-only  # scrape and extract only, skip site rebuild
python run.py --build-only   # rebuild site from existing data, skip scraping
python run.py --status       # show stats: total restaurants, sources, last update
```

## Setup & Configuration

### Requirements
- Python 3.10+
- OpenAI API key (set as `OPENAI_API_KEY` in `.env`)

### First-Time Setup
```bash
git clone https://github.com/jcubb/chef-recs.git
cd chef-recs
# Activate your venv
pip install -r requirements.txt
cp .env.example .env
# Edit .env to add OPENAI_API_KEY=sk-...
```

### GitHub Pages Setup
- In GitHub repo settings → Pages → set source to "Deploy from a branch"
- Branch: `master`, folder: `/docs`
- Site will be live at `jcubb.github.io/chef-recs`

### Dependencies (`requirements.txt`)
```
openai
requests
beautifulsoup4
python-slugify
python-dotenv
```

### `.gitignore`
```
.env
__pycache__/
*.pyc
```

Note: `data/` and `docs/` are NOT gitignored — they are committed and pushed so GitHub Pages can serve the site and data persists in the repo.

## Gotchas & Known Issues

### Windows terminal encoding
Avoid non-ASCII characters (like `→`) in `print()` statements. The Windows cp1252 terminal encoding will raise a `UnicodeEncodeError`. Use `->` instead.

### Re-processing a failed article
If an article was processed but extracted 0 restaurants (e.g. due to an API error), remove it from `data/processed.json` and re-run:
```bash
# Edit data/processed.json, delete the entry for the failed article URL
python run.py --scrape-only
```

### City inconsistency
The OpenAI extractor may label Brooklyn restaurants as either "Brooklyn" or "New York". The `city_filter` in `sources.json` covers both — always include all borough names when configuring a new NYC source.

### Nominatim geocoding misses
Some restaurants (especially newer or smaller spots) aren't in OpenStreetMap. The 3-tier fallback resolves ~80% of cases. Remaining restaurants appear in the list view only (no map pin).

### Duplicate restaurants
Deduplication uses `slugify(name + neighborhood)`. If the same restaurant is extracted twice with different neighborhood values (e.g. "" vs "Manhattan"), two entries will be created. This is rare but can happen when the same restaurant appears in multiple articles.

## Design Decisions & Notes

- **Why OpenAI over Anthropic**: OpenAI's `response_format: json_object` enforces valid JSON output reliably. gpt-4o-mini is fast and cheap for this extraction task.
- **Why JSON over SQLite**: The dataset is small (hundreds of restaurants at most). JSON is human-readable, easy to inspect, and plays well with git diffs.
- **Why Leaflet over Google Maps**: Free, no API key, open source.
- **Why GitHub Pages over Vercel/Render**: Zero config, free, no server to manage.
- **Nominatim for geocoding**: Free, no API key. Tradeoff is rate limiting (1 req/sec) and occasional misses for newer/smaller restaurants.

## Future Enhancements (Parking Lot)

- Resy integration: investigate whether restaurants can be added to a Resy list (browser automation or import)
- Additional sources: other food Substacks, Eater, Infatuation, etc.
- Notifications: alert when new restaurants are added (email, SMS, etc.)
- Categories/tags: user-defined tags (e.g., "date night", "quick lunch")
- "Visited" tracking: mark restaurants as visited with notes
- Google Maps list export: generate a format importable to Google Maps saved lists
