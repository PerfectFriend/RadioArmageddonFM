#!/usr/bin/env python3
"""
Hybrid News Scraper for Radio Pipeline
Primary: RSS feeds (instant, reliable)
Secondary: X.com top accounts (optional, slower)
"""

import asyncio
import feedparser
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from playwright.async_api import async_playwright

# ─── Config ──────────────────────────────────────────────────────────────
PROFILE_DIR = Path(r"C:\Users\tomas\.agent-browser\profiles\xcom")
OUTPUT_DIR = Path(r"C:\Users\tomas\ai-radio")
HEADLESS = True
SCROLL_ROUNDS = 1
WAIT_TIMEOUT = 45000
NAV_TIMEOUT = 60000

# RSS Feeds by category (instant, no auth needed)
RSS_FEEDS = {
    "ai_ml": [
        "https://huggingface.co/blog/feed.xml",
        "https://openai.com/blog/rss.xml",
        "https://deepmind.com/blog/feed.xml",
        "https://www.anthropic.com/feed.xml",
        "https://karpathy.github.io/feed.xml",
        "https://feeds.feedburner.com/oreilly/radar/artificial-intelligence",
    ],
    "tech": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://www.wired.com/feed/rss",
        "https://arstechnica.com/feed/",
        "https://www.reuters.com/technology/feed/",
    ],
    "space": [
        "https://www.nasa.gov/rss/dyn/breaking_news.rss",
        "https://www.spacex.com/news/rss/",
        "https://www.space.com/feeds/all",
        "https://www.nasaspaceflight.com/feed/",
    ],
    "politics": [
        "https://feeds.reuters.com/reuters/politicsNews",
        "https://feeds.reuters.com/reuters/worldNews",
        "https://www.bbc.co.uk/feeds/news/world/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
        "https://www.washingtonpost.com/politics/rss.xml",
    ],
    "war": [
        "https://www.reuters.com/world/ukraine/feed/",
        "https://www.bbc.co.uk/feeds/news/world/europe/rss.xml",
        "https://www.understandingwar.org/feed",
        "https://isw.pub/feed.xml",
    ],
    "music": [
        "https://pitchfork.com/rss/news/",
        "https://www.rollingstone.com/music/music-news/feed/",
        "https://www.billboard.com/feed/",
        "https://www.nme.com/feed/",
    ],
    "cinema": [
        "https://variety.com/feed/",
        "https://www.hollywoodreporter.com/feed/",
        "https://deadline.com/feed/",
        "https://www.theverge.com/film/rss/index.xml",
    ],
    "finance": [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://www.bloomberg.com/feed/",
        "https://www.ft.com/rss/home/world",
        "https://www.wsj.com/xml/rss/3_7014.xml",
    ],
    "crypto": [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://www.theblock.co/rss",
        "https://cointelegraph.com/rss",
        "https://decrypt.co/feed",
        "https://blog.chainalysis.com/feed/",
    ],
}

# X.com top accounts only (optional, for enrichment)
X_TOP_ACCOUNTS = {
    "ai_ml": ["karpathy", "ylecun", "OpenAI", "AnthropicAI", "GoogleDeepMind", "huggingface"],
    "tech": ["TechCrunch", "TheVerge", "Wired"],
    "space": ["NASA", "SpaceX", "elonmusk"],
    "politics": ["Reuters", "AP", "BBCWorld"],
    "war": ["WarMonitor3", "OSINTdefender"],
    "music": ["pitchfork", "RollingStone"],
    "cinema": ["Variety", "THR"],
    "finance": ["Bloomberg", "ReutersBiz"],
    "crypto": ["VitalikButerin", "cz_binance"],
}

# Engagement weights
ENGAGEMENT_WEIGHTS = {
    "views": 0.1,
    "likes": 2.0,
    "retweets": 3.0,
    "replies": 1.5,
    "quotes": 1.0,
}
MIN_ENGAGEMENT_SCORE = 30
MAX_AGE_HOURS = 24


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
    # X.com enrichment (optional)
    author: str = ""
    author_handle: str = ""
    views: int = 0
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    quotes: int = 0
    engagement_score: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


# ─── RSS Scraper (Primary - Fast) ────────────────────────────────────────
class RSSScraper:
    @staticmethod
    def parse_feed(url: str, category: str) -> List[NewsItem]:
        items = []
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:  # Limit per feed
                # Parse date
                pub_date = ""
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6]).isoformat() + "Z"
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    pub_date = datetime(*entry.updated_parsed[:6]).isoformat() + "Z"

                # Check freshness
                if pub_date and not RSSScraper._is_fresh(pub_date):
                    continue

                # Generate ID
                item_id = entry.get('id', entry.get('link', ''))
                item_id = re.sub(r'[^a-zA-Z0-9]', '_', item_id)[:50]

                # Summary
                summary = entry.get('summary', entry.get('description', ''))
                summary = re.sub(r'<[^>]+>', '', summary)  # Strip HTML
                summary = summary[:500]

                item = NewsItem(
                    id=item_id,
                    title=entry.get('title', '').strip(),
                    summary=summary,
                    url=entry.get('link', ''),
                    source=feed.feed.get('title', url),
                    category=category,
                    published_at=pub_date,
                    scraped_at=datetime.utcnow().isoformat() + "Z",
                )
                items.append(item)
        except Exception as e:
            print(f"  ⚠️ RSS error for {url}: {e}")
        return items

    @staticmethod
    def _is_fresh(date_str: str, max_hours: int = MAX_AGE_HOURS) -> bool:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return datetime.now(dt.tzinfo) - dt < timedelta(hours=max_hours)
        except:
            return True

    def scrape_category(self, category: str) -> List[NewsItem]:
        all_items = []
        urls = RSS_FEEDS.get(category, [])
        for url in urls:
            print(f"  📡 RSS: {url[:60]}...")
            items = self.parse_feed(url, category)
            print(f"    → {len(items)} items")
            all_items.extend(items)
        return all_items


# ─── X.com Scraper (Secondary - Optional Enrichment) ────────────────────
class XScraper:
    def __init__(self):
        self.browser = None
        self.page = None

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 720},
        )
        self.page = await self.browser.new_page()
        await self.page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        return self

    async def __aexit__(self, *args):
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()

    async def get_user_tweets(self, handle: str, max_tweets: int = 10) -> List[Dict]:
        """Get recent tweets from a specific user profile."""
        url = f"https://x.com/{handle}"
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await self.page.wait_for_selector('[data-testid="tweet"]', timeout=30000)

            tweets = []
            tweet_elements = await self.page.query_selector_all('[data-testid="tweet"]')

            for el in tweet_elements[:max_tweets]:
                try:
                    data = await self._extract_tweet(el, handle)
                    if data:
                        tweets.append(data)
                except:
                    continue

            return tweets
        except Exception as e:
            print(f"  ⚠️ X.com error for @{handle}: {e}")
            return []

    async def _extract_tweet(self, element, handle: str) -> Optional[Dict]:
        try:
            link_el = await element.query_selector('a[href*="/status/"]')
            if not link_el:
                return None
            href = await link_el.get_attribute("href")
            tweet_id = href.split("/status/")[-1].split("?")[0].split("/")[0]

            text_el = await element.query_selector('[data-testid="tweetText"]')
            text = await text_el.inner_text() if text_el else ""

            time_el = await element.query_selector('time')
            timestamp = await time_el.get_attribute("datetime") if time_el else ""

            metrics = {}
            for action, testid in [("replies", "reply"), ("retweets", "retweet"), ("likes", "like")]:
                try:
                    btn = await element.query_selector(f'[data-testid="{testid}"]')
                    if btn:
                        aria = await btn.get_attribute("aria-label")
                        metrics[action] = self._parse_count(aria) if aria else 0
                except:
                    metrics[action] = 0

            return {
                "id": tweet_id,
                "text": text,
                "author_handle": handle,
                "url": f"https://x.com/{handle}/status/{tweet_id}",
                "timestamp": timestamp,
                "metrics": metrics,
            }
        except:
            return None

    @staticmethod
    def _parse_count(text: str) -> int:
        if not text:
            return 0
        text = text.replace(",", "").strip().upper()
        try:
            if "K" in text:
                return int(float(text.replace("K", "")) * 1000)
            elif "M" in text:
                return int(float(text.replace("M", "")) * 1_000_000)
            else:
                match = re.search(r"[\d.]+", text)
                return int(float(match.group())) if match else 0
        except:
            return 0


# ─── Engagement Scoring ──────────────────────────────────────────────────
def calc_engagement(metrics: Dict) -> float:
    score = 0.0
    for metric, weight in ENGAGEMENT_WEIGHTS.items():
        score += metrics.get(metric, 0) * weight
    return round(score, 2)


# ─── Main Pipeline ───────────────────────────────────────────────────────
async def scrape_rss_all() -> Dict[str, List[NewsItem]]:
    """Scrape all RSS feeds (primary, fast)."""
    print("\n📡 SCRAPING RSS FEEDS (Primary)")
    print("=" * 50)

    rss = RSSScraper()
    results = {}

    for category in RSS_FEEDS.keys():
        print(f"\n📂 {category}")
        items = rss.scrape_category(category)
        # Dedup by URL
        seen = set()
        unique = []
        for item in items:
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)
        results[category] = unique
        print(f"  ✅ {len(unique)} unique items")

    return results


async def enrich_with_xcom(rss_results: Dict) -> Dict:
    """Optional: enrich top items with X.com data."""
    print("\n🐦 ENRICHING WITH X.COM (Secondary)")
    print("=" * 50)

    async with XScraper() as scraper:
        for category, handles in X_TOP_ACCOUNTS.items():
            if category not in rss_results:
                continue
            print(f"\n📂 {category} - checking {len(handles)} accounts")
            for handle in handles[:3]:  # Limit to 3 accounts per category
                print(f"  🔍 @{handle}")
                tweets = await scraper.get_user_tweets(handle, max_tweets=5)
                for tw in tweets:
                    metrics = tw.get("metrics", {})
                    score = calc_engagement(metrics)
                    if score >= MIN_ENGAGEMENT_SCORE:
                        # Add as enriched item
                        item = NewsItem(
                            id=tw["id"],
                            title=tw["text"][:100],
                            summary=tw["text"],
                            url=tw["url"],
                            source=f"X: @{handle}",
                            category=category,
                            published_at=tw.get("timestamp", ""),
                            scraped_at=datetime.utcnow().isoformat() + "Z",
                            author_handle=handle,
                            views=metrics.get("views", 0),
                            likes=metrics.get("likes", 0),
                            retweets=metrics.get("retweets", 0),
                            replies=metrics.get("replies", 0),
                            quotes=metrics.get("quotes", 0),
                            engagement_score=score,
                        )
                        rss_results[category].append(item)
                        print(f"    ✅ Added tweet (score: {score})")
                await asyncio.sleep(2)

    return rss_results


def save_results(results: Dict[str, List[NewsItem]]):
    """Save to JSON."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "news_latest.json"

    output = {
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "categories": {
            cat: [item.to_dict() for item in items]
            for cat, items in results.items()
        }
    }
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\n💾 Saved to {out_path}")


def print_summary(results: Dict):
    total = sum(len(items) for items in results.values())
    print(f"\n📊 SUMMARY: {total} items across {len(results)} categories")
    for cat, items in results.items():
        if items:
            top = max(items, key=lambda x: x.engagement_score) if items else None
            print(f"  {cat}: {len(items)} | Top score: {top.engagement_score if top else 0}")


# ─── Main ────────────────────────────────────────────────────────────────
async def main():
    print("🚀 HYBRID NEWS SCRAPER")
    print(f"📁 Output: {OUTPUT_DIR}")
    print(f"📡 RSS feeds: {sum(len(v) for v in RSS_FEEDS.values())} sources")
    print(f"🐦 X.com accounts: {sum(len(v) for v in X_TOP_ACCOUNTS.values())} accounts")

    # Phase 1: RSS (fast, primary)
    rss_results = await scrape_rss_all()

    # Phase 2: X.com enrichment (optional, comment out if not needed)
    # final_results = await enrich_with_xcom(rss_results)
    final_results = rss_results  # Skip X.com for speed

    # Save
    save_results(final_results)
    print_summary(final_results)

    return final_results


if __name__ == "__main__":
    asyncio.run(main())