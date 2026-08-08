#!/usr/bin/env python3
"""
Fast News Scraper for Radio Pipeline
RSS only, optimized for speed. Outputs JSON for TTS pipeline.
"""

import feedparser
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── Config ──────────────────────────────────────────────────────────────
OUTPUT_DIR = Path(r"C:\Users\tomas\ai-radio")
MAX_AGE_HOURS = 24
MAX_WORKERS = 8
TIMEOUT = 10

# RSS Feeds by category (tested working)
RSS_FEEDS = {
    "ai_ml": [
        "https://huggingface.co/blog/feed.xml",
        "https://openai.com/blog/rss.xml",
        "https://deepmind.com/blog/feed.xml",
        "https://www.anthropic.com/feed.xml",
        "https://karpathy.github.io/feed.xml",
    ],
    "tech": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://www.wired.com/feed/rss",
        "https://arstechnica.com/feed/",
    ],
    "space": [
        "https://www.nasa.gov/rss/dyn/breaking_news.rss",
        "https://www.space.com/feeds/all",
    ],
    "politics": [
        "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
        "https://www.washingtonpost.com/politics/rss.xml",
    ],
    "war": [
        "https://www.reuters.com/world/ukraine/feed/",
        "https://www.understandingwar.org/feed",
    ],
    "music": [
        "https://pitchfork.com/rss/news/",
        "https://www.rollingstone.com/music/music-news/feed/",
        "https://www.billboard.com/feed/",
    ],
    "cinema": [
        "https://variety.com/feed/",
        "https://www.hollywoodreporter.com/feed/",
        "https://deadline.com/feed/",
    ],
    "finance": [
        "https://www.bloomberg.com/feed/",
        "https://www.ft.com/rss/home/world",
    ],
    "crypto": [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://www.theblock.co/rss",
        "https://cointelegraph.com/rss",
    ],
}

# ─── Data Models ─────────────────────────────────────────────────────────
@dataclass
class NewsItem:
    id: str
    title: str
    summary: str
    url: str
    source: str
    category: str
    published_at: str
    scraped_at: str

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Scraper Functions ───────────────────────────────────────────────────
def fetch_feed(url: str, category: str, timeout: int = TIMEOUT) -> List[dict]:
    """Fetch and parse a single RSS feed."""
    items = []
    try:
        feed = feedparser.parse(url, request_headers={'User-Agent': 'RadioNewsBot/1.0'})
        if feed.bozo and feed.bozo_exception:
            print(f"  ⚠️ {url}: {feed.bozo_exception}")

        for entry in feed.entries[:15]:
            # Parse date
            pub_date = ""
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6]).isoformat() + "Z"
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                pub_date = datetime(*entry.updated_parsed[:6]).isoformat() + "Z"

            # Check freshness
            if pub_date and not is_fresh(pub_date):
                continue

            # Summary
            summary = entry.get('summary', entry.get('description', ''))
            summary = re.sub(r'<[^>]+>', '', summary)[:500]

            item = NewsItem(
                id=re.sub(r'[^a-zA-Z0-9]', '_', entry.get('id', entry.get('link', '')))[:50],
                title=entry.get('title', '').strip(),
                summary=summary,
                url=entry.get('link', ''),
                source=feed.feed.get('title', url),
                category=category,
                published_at=pub_date,
                scraped_at=datetime.utcnow().isoformat() + "Z",
            )
            items.append(item.to_dict())
    except Exception as e:
        print(f"  ❌ {url}: {e}")
    return items


def is_fresh(date_str: str, max_hours: int = 24) -> bool:
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return datetime.now(dt.tzinfo) - dt < timedelta(hours=max_hours)
    except:
        return True


@dataclass
class NewsItem:
    id: str
    title: str
    summary: str
    url: str
    source: str
    category: str
    published_at: str
    scraped_at: str

    def to_dict(self) -> dict:
        return asdict(self)


def scrape_category(category: str) -> List[dict]:
    """Scrape all feeds for a category in parallel."""
    urls = RSS_FEEDS.get(category, [])
    print(f"📂 {category} ({len(urls)} feeds)")

    all_items = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(fetch_feed, url, category): url for url in urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                items = future.result(timeout=15)
                print(f"  ✅ {url[:50]}: {len(items)} items")
                all_items.extend(items)
            except Exception as e:
                print(f"  ❌ {url}: {e}")

    # Dedup by URL
    seen = set()
    unique = []
    for item in all_items:
        if item['url'] not in seen:
            seen.add(item['url'])
            unique.append(item)

    print(f"  📊 {category}: {len(unique)} unique items")
    return unique


def main():
    print("⚡ FAST NEWS SCRAPER")
    print(f"📁 Output: C:\\Users\\tomas\\ai-radio")
    print(f"📡 Categories: {len(RSS_FEEDS)} | Total feeds: {sum(len(v) for v in RSS_FEEDS.values())}")

    results = {}
    total = 0

    for category in RSS_FEEDS.keys():
        items = scrape_category(category)
        results[category] = items
        total += len(items)

    # Save
    OUTPUT_DIR = Path(r"C:\Users\tomas\ai-radio")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output = {
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "categories": results
    }
    out_path = OUTPUT_DIR / "news_latest.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))

    print(f"\n💾 Saved to {out_path}")
    print(f"\n📊 SUMMARY: {total} items across {len(results)} categories")
    for cat, items in results.items():
        print(f"  {cat}: {len(items)}")

    return results


if __name__ == "__main__":
    import json
    main()