import time
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "chef-recs/1.0 (github.com/jcubb/chef-recs; restaurant recommendation aggregator)"
}

REQUEST_DELAY = 1.5  # seconds between requests


def fetch_article_urls(archive_url: str) -> list[str]:
    """Fetch all article URLs from a Substack archive page, handling pagination."""
    urls = []
    offset = 0

    while True:
        paginated_url = f"{archive_url}?sort=new&offset={offset}" if offset else archive_url
        response = requests.get(paginated_url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        links = soup.select("a.pencraft")
        if not links:
            # Try alternate selector patterns Substack uses
            links = soup.select("a[href*='/p/']")

        page_urls = []
        for a in links:
            href = a.get("href", "")
            if "/p/" in href and href not in urls and href not in page_urls:
                # Normalize to full URL
                if href.startswith("http"):
                    page_urls.append(href)
                else:
                    base = archive_url.replace("/archive", "")
                    page_urls.append(base.rstrip("/") + "/" + href.lstrip("/"))

        if not page_urls:
            break

        urls.extend(page_urls)
        offset += len(page_urls)

        # If the page returned fewer links than expected, we've hit the end
        if len(page_urls) < 12:
            break

        time.sleep(REQUEST_DELAY)

    return list(dict.fromkeys(urls))  # deduplicate while preserving order


def fetch_article(url: str) -> dict | None:
    """
    Fetch a single Substack article. Returns dict with title and text,
    or None if the article is paywalled / inaccessible.
    """
    time.sleep(REQUEST_DELAY)
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  [scraper] Failed to fetch {url}: {e}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # Extract title
    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else "Untitled"

    # Detect paywall
    paywall = soup.select_one(".paywall, .paywall-content, [class*='paywall']")
    if paywall:
        print(f"  [scraper] Skipping paywalled article: {title}")
        return None

    # Extract main article body
    body = (
        soup.select_one("div.available-content")
        or soup.select_one("article")
        or soup.select_one("div.post-content")
        or soup.select_one("div.body")
    )

    if not body:
        print(f"  [scraper] Could not find article body for: {title}")
        return None

    text = body.get_text(separator="\n", strip=True)

    # Skip very short articles (likely just teasers)
    if len(text) < 200:
        print(f"  [scraper] Article too short (likely teaser), skipping: {title}")
        return None

    # Extract publish date from <time> tag
    time_tag = soup.find("time")
    article_date = ""
    if time_tag:
        dt = time_tag.get("datetime", "")
        article_date = dt[:10] if dt else ""  # keep YYYY-MM-DD portion only

    return {"title": title, "text": text, "url": url, "date": article_date}


def scrape_new_articles(sources: list[dict], processed_urls: set[str]) -> list[dict]:
    """
    For each enabled source, fetch all article URLs, filter out already-processed ones,
    then fetch and return the full text of new articles.

    Returns list of dicts: {url, title, text, source_name}
    """
    new_articles = []

    for source in sources:
        if not source.get("enabled"):
            continue

        name = source["name"]
        archive_url = source["archive_url"]
        print(f"[scraper] Checking archive for '{name}'...")

        try:
            all_urls = fetch_article_urls(archive_url)
        except Exception as e:
            print(f"[scraper] Failed to fetch archive for '{name}': {e}")
            continue

        url_pattern = source.get("url_pattern", "")
        if url_pattern:
            all_urls = [u for u in all_urls if url_pattern in u]
            print(f"[scraper] Filtered to {len(all_urls)} articles matching '{url_pattern}'.")

        new_urls = [u for u in all_urls if u not in processed_urls]
        print(f"[scraper] Found {len(all_urls)} articles, {len(new_urls)} new.")

        for url in new_urls:
            print(f"  [scraper] Fetching: {url}")
            article = fetch_article(url)
            if article:
                article["source_name"] = name
                new_articles.append(article)

    return new_articles
