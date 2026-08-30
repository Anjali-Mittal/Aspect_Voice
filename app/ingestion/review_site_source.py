"""Scrapes public review pages directly. No API, no key, no CC.

Two extraction modes, picked per-site in config (sites.<n>.extraction_mode):

- "jsonld": generic, recursive search through a page's <script type=
  application/ld+json> blocks for any {"@type": "Review", "reviewBody": ...}
  object, wherever it's nested. Robust — schema.org shape doesn't change with
  site redesigns. Some sites only embed one sample review this way (SEO rich
  snippet, not the full list) — that's a site limitation, not a scraper bug.

- "css": selector-driven, for sites that render reviews as plain server-side
  HTML with stable (non-hashed) class names. Selectors verified against real
  page HTML, kept in config, not code.

A site with CSS-in-JS hashed classnames (e.g. class="o-kI vFzWDb") is not
scrapable by selector — those hashes regenerate on every deploy. Such a site
needs a jsonld source instead, or is left out.
"""
import time
import json
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from app.config import get_config

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _fetch(url: str) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException:
        return None


def _find_reviews_in_jsonld(node) -> list[dict]:
    """Recursively walk any JSON structure, collecting schema.org Review objects."""
    found = []
    if isinstance(node, dict):
        if node.get("@type") == "Review" and (node.get("reviewBody") or node.get("description")):
            found.append(node)
        else:
            for v in node.values():
                found.extend(_find_reviews_in_jsonld(v))
    elif isinstance(node, list):
        for item in node:
            found.extend(_find_reviews_in_jsonld(item))
    return found


def _scrape_jsonld(site_cfg: dict, product_name: str) -> list[dict]:
    soup = _fetch(site_cfg["url"])
    if soup is None:
        return []

    items = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            continue
        for review in _find_reviews_in_jsonld(data):
            text = review.get("reviewBody") or review.get("description") or ""
            if not text.strip():
                continue
            author_field = review.get("author")
            author = author_field.get("name") if isinstance(author_field, dict) else author_field
            date_str = review.get("datePublished")
            try:
                created = datetime.fromisoformat(date_str.replace("Z", "+00:00")) if date_str else datetime.utcnow()
            except ValueError:
                created = datetime.utcnow()

            source_id = f"{site_cfg['name']}_{hash(text) & 0xffffffff}"
            items.append({
                "source": f"review_site_{site_cfg['name']}",
                "source_id": source_id,
                "product_name": product_name,
                "text": text,
                "author": author,
                "url": site_cfg["url"],
                "created_at": created,
                "meta": {"site": site_cfg["name"], "rating": (review.get("reviewRating") or {}).get("ratingValue")},
            })
    return items


def _scrape_css(site_cfg: dict, product_name: str) -> list[dict]:
    items = []
    base_url = site_cfg["url"]
    max_pages = site_cfg.get("max_pages", 1)
    page_param = site_cfg.get("page_param")

    for page in range(1, max_pages + 1):
        url = base_url if page == 1 or not page_param else f"{base_url}?{page_param}={page}"
        soup = _fetch(url)
        if soup is None:
            break

        cards = soup.select(site_cfg["review_container_selector"])
        if not cards:
            break

        for card in cards:
            text_el = card.select_one(site_cfg["text_selector"])
            if not text_el:
                continue
            text = text_el.get_text(strip=True)
            if not text:
                continue

            author_el = card.select_one(site_cfg["author_selector"]) if site_cfg.get("author_selector") else None
            source_id = f"{site_cfg['name']}_{hash(text) & 0xffffffff}"

            items.append({
                "source": f"review_site_{site_cfg['name']}",
                "source_id": source_id,
                "product_name": product_name,
                "text": text,
                "author": author_el.get_text(strip=True) if author_el else None,
                "url": url,
                "created_at": datetime.utcnow(),
                "meta": {"site": site_cfg["name"], "page": page},
            })

        time.sleep(site_cfg.get("delay_seconds", 1.5))  # polite delay, avoid rate-limit/ban

    return items


_MODE_FN = {"jsonld": _scrape_jsonld, "css": _scrape_css}


def fetch_review_site_feedback() -> list[dict]:
    cfg = get_config()
    rcfg = cfg["sources"].get("review_sites", {})
    if not rcfg.get("enabled"):
        return []

    product_name = cfg["target"]["product_name"]
    all_items = []
    for site_cfg in rcfg.get("sites", []):
        fn = _MODE_FN.get(site_cfg["extraction_mode"])
        if not fn:
            continue
        all_items.extend(fn(site_cfg, product_name))
    return all_items
