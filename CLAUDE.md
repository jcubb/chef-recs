# chef-recs

## Project Overview

A tool that scrapes restaurant recommendations from food-focused Substack newsletters (starting with [Eating with Experts](https://eatingwithexperts.substack.com)), extracts structured restaurant data using the Claude API, stores it in a local JSON database, and generates a static site with list and map views — hosted for free via GitHub Pages.

**Repo:** `github.com/jcubb/chef-recs`
**Live site:** `jcubb.github.io/chef-recs`

## Architecture

```
Substack newsletters
        │
        ▼
   Scraper (requests + BeautifulSoup)
   - Fetches archive page, finds article URLs
   - Skips already-processed articles
        │
        ▼
   Extractor (Anthropic SDK)
   - Sends article text to Claude API
   - Returns structured JSON per restaurant
        │
        ▼
   Data Store (JSON file)
   - data/restaurants.json — the restaurant collection
   - data/processed.json — list of already-processed article URLs
   - Deduplication by restaurant name + neighborhood
        │
        ▼
   Site Generator
   - Builds docs/index.html from restaurant data
   - List view + Leaflet.js map with pins
   - Filterable by neighborhood, cuisine, recommending chef
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
├── .env                   # ANTHROPIC_API_KEY (gitignored)
├── .gitignore
├── src/
│   ├── __init__.py
│   ├── scraper.py         # Substack fetching logic
│   ├── extractor.py       # Claude API extraction logic
│   ├── store.py           # JSON read/write, dedup logic
│   └── site_generator.py  # builds static HTML into docs/
├── data/
│   ├── restaurants.json   # restaurant records
│   └── processed.json     # tracked article URLs + processing timestamps
├── docs/                  # GitHub Pages source
│   └── index.html         # generated static site (list + map)
└── sources.json           # configured Substack sources
```

## Component Details

### 1. Source Configuration (`sources.json`)

```json
[
  {
    "name": "Eating with Experts",
    "archive_url": "https://eatingwithexperts.substack.com/archive",
    "enabled": true
  }
]
```

Designed to be extensible — user can add more Substack newsletters later.

### 2. Scraper (`src/scraper.py`)

- Fetches the Substack archive page for each enabled source
- Substack archive pages are server-rendered HTML with links to each post
- Parses out individual article URLs using BeautifulSoup
- Compares against `data/processed.json` to identify new/unprocessed articles
- For each new article, fetches the full article page and extracts the article body text (the main content area, stripping nav/footer/sidebar)
- Returns a list of `{url, title, text, source_name}` dicts for new articles

**Important notes on Substack scraping:**
- Substack may paginate their archive — handle pagination if present (typically infinite scroll loaded via offset parameter)
- Rate limit requests (1-2 second delay between fetches) to be respectful
- Use a reasonable User-Agent header
- Some Substack posts may be paywalled — skip those gracefully if content isn't accessible

### 3. Extractor (`src/extractor.py`)

- Takes article text and sends it to the Claude API (claude-sonnet-4-20250514)
- Uses a structured prompt asking Claude to extract all restaurant recommendations
- Requests JSON output with this schema per restaurant:

```json
{
  "name": "Thai Diner",
  "neighborhood": "Nolita",
  "city": "New York",
  "cuisine": "Thai-American",
  "recommended_dishes": ["crab fried rice"],
  "recommended_by": ["Chef Ben Selman", "Chef Suzanne Cupps"],
  "context": "Ben's go-to spot for dining out; also picked by Suzanne Cupps from Lola's",
  "source_url": "https://eatingwithexperts.substack.com/p/where-chefs-eat-in-nyc",
  "source_name": "Eating with Experts"
}
```

- The prompt should instruct Claude to:
  - Only extract restaurants that are being recommended (not the chef's own restaurant, unless it's also being recommended by someone else)
  - Include neighborhood if mentioned; leave empty string if not
  - Include city — most will be NYC but some posts may cover other cities
  - Extract specific dish recommendations if mentioned
  - Note which chef(s) recommended each place
  - Provide brief context for the recommendation

- Use `response_format` or a strong system prompt to ensure valid JSON output

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

**Deduplication logic:**
- Generate an ID by slugifying `name + neighborhood` (e.g., "thai-diner-nolita")
- When a duplicate is found, merge: append new chefs to `recommended_by`, merge `recommended_dishes` (deduplicated), append new context
- This means a restaurant recommended by 3 different chefs across 3 articles will have one entry with all three listed

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

- After extraction, geocode restaurants that have `latitude: null`
- Use a free geocoding service — **Nominatim (OpenStreetMap)** is free, no API key needed
  - Endpoint: `https://nominatim.openstreetmap.org/search`
  - Query with restaurant name + neighborhood + city
  - Rate limit: max 1 request per second (required by Nominatim usage policy)
  - Set a custom User-Agent header identifying the project
- If geocoding fails (restaurant not found), leave lat/lng as null — it will appear in the list but not on the map
- Geocode only on first add — don't re-geocode existing entries

### 6. Site Generator (`src/site_generator.py`)

- Reads `data/restaurants.json`
- Generates a single `docs/index.html` file — fully self-contained
- The page should include:
  - **List view**: all restaurants in a scrollable list, showing name, neighborhood, cuisine, who recommended it, and dishes to try
  - **Map view**: Leaflet.js map with pins for all geocoded restaurants; clicking a pin shows a popup with restaurant details
  - **Toggle** between list and map views (or show both — side by side on desktop, stacked on mobile)
  - **Filters**: filter by neighborhood, cuisine type, recommending chef, or source newsletter
  - **Search**: simple text search across restaurant names
  - **Mobile-friendly**: this will primarily be viewed on a phone, so responsive design is critical
- Use Leaflet.js via CDN (no build step needed)
- Embed the restaurant data as a JSON object directly in the HTML file (keeps it self-contained, no separate data fetch needed)
- Style it clean and simple — dark or light theme, easy to read, not cluttered

### 7. CLI Entry Point (`run.py`)

```python
"""
Usage:
  python run.py                # full pipeline: scrape → extract → geocode → build site
  python run.py --scrape-only  # just scrape and extract, don't rebuild site
  python run.py --build-only   # just rebuild site from existing data
  python run.py --status       # show stats: total restaurants, sources, last update
"""
```

- Runs the full pipeline by default
- Prints progress to stdout (which articles are being processed, how many restaurants extracted, etc.)
- Handles errors gracefully — if one article fails extraction, continue with the rest

## Setup & Configuration

### Requirements
- Python 3.10+
- Anthropic API key

### First-Time Setup
```bash
git clone https://github.com/jcubb/chef-recs.git
cd chef-recs
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env to add ANTHROPIC_API_KEY
```

### GitHub Pages Setup
- In GitHub repo settings → Pages → set source to "Deploy from a branch"
- Branch: `main`, folder: `/docs`
- Site will be live at `jcubb.github.io/chef-recs`

### Dependencies (`requirements.txt`)
```
anthropic
requests
beautifulsoup4
python-slugify
python-dotenv
```

### `.gitignore`
```
.env
venv/
__pycache__/
*.pyc
```

Note: `data/` and `docs/` are NOT gitignored — they are committed and pushed so GitHub Pages can serve the site and data persists in the repo.

## Design Decisions & Notes

- **Why JSON over SQLite**: The dataset is small (hundreds of restaurants at most). JSON is human-readable, easy to inspect, and plays well with git diffs. If scale becomes an issue, migration to SQLite is straightforward.
- **Why Leaflet over Google Maps**: Free, no API key, open source. Works great for this use case.
- **Why Claude claude-sonnet-4-20250514 for extraction**: Good balance of quality and cost for structured extraction. Upgrade to Opus if extraction quality is insufficient.
- **Why GitHub Pages over Vercel/Render**: Zero config, free, no server to manage. Fits the "run locally, push to update" workflow perfectly.
- **Nominatim for geocoding**: Free, no API key. Tradeoff is rate limiting (1 req/sec) and occasional misses for newer/smaller restaurants. If this becomes a problem, Google Geocoding API is more reliable but requires a key.

## Future Enhancements (Parking Lot)

- Resy integration: investigate whether restaurants can be added to a Resy list (browser automation or import)
- Additional sources: other food Substacks, Eater, Infatuation, etc.
- Notifications: alert when new restaurants are added (email, SMS, etc.)
- Categories/tags: user-defined tags (e.g., "date night", "quick lunch")
- "Visited" tracking: mark restaurants as visited with notes
- Google Maps list export: generate a format importable to Google Maps saved lists
