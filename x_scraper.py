#!/usr/bin/env python3
"""
X.com News Scraper for Radio Pipeline
Uses agent-browser profile (xcom) for authenticated reading.
Returns structured tweets with engagement scoring.
"""

import asyncio
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
HEADLESS = True  # False for debugging
SCROLL_ROUNDS = 2
WAIT_TIMEOUT = 60000
NAV_TIMEOUT = 90000

# Simplified queries - avoid complex OR chains that trigger anti-bot
CATEGORY_QUERIES = {
    "ai_ml": [
        "from:karpathy",
        "from:ylecun",
        "from:OpenAI",
        "from:AnthropicAI",
        "AI breakthrough lang:en",
    ],
    "tech": [
        "from:TechCrunch",
        "from:TheVerge",
        "from:Wired",
        "tech news lang:en",
    ],
    "space": [
        "from:NASA",
        "from:SpaceX",
        "from:elonmusk",
        "space launch lang:en",
    ],
    "politics": [
        "from:Reuters",
        "from:AP",
        "from:BBCWorld",
        "breaking news politics lang:en",
    ],
    "war": [
        "from:WarMonitor3",
        "from:OSINTdefender",
        "ukraine war update lang:en",
    ],
    "music": [
        "from:pitchfork",
        "from:RollingStone",
        "new album release lang:en",
    ],
    "cinema": [
        "from:Variety",
        "from:THR",
        "movie trailer lang:en",
    ],
    "finance": [
        "from:Bloomberg",
        "from:ReutersBiz",
        "stock market today lang:en",
    ],
    "crypto": [
        "from:VitalikButerin",
        "from:cz_binance",
        "bitcoin price lang:en",
    ],
}

# Simpler queries per category (rotate through accounts)
CATEGORY_SIMPLE_QUERIES = {
    "ai_ml": ["karpathy", "OpenAI", "AnthropicAI", "huggingface", "machine learning"],
    "tech": ["TechCrunch", "TheVerge", "Wired", "tech news"],
    "space": ["NASA", "SpaceX", "elonmusk", "rocket launch"],
    "politics": ["Reuters", "AP", "BBCWorld", "breaking news"],
    "war": ["WarMonitor3", "OSINTdefender", "ukraine war"],
    "music": ["pitchfork", "RollingStone", "new album"],
    "cinema": ["Variety", "THR", "movie trailer"],
    "finance": ["Bloomberg", "ReutersBiz", "stock market"],
    "crypto": ["VitalikButerin", "cz_binance", "bitcoin"],
}

# Engagement scoring weights
ENGAGEMENT_WEIGHTS = {
    "views": 0.1,
    "likes": 2.0,
    "retweets": 3.0,
    "replies": 1.5,
    "quotes": 1.0,
}

MIN_ENGAGEMENT_SCORE = 50  # Filter threshold
MAX_AGE_HOURS = 24  # Only fresh news


# ─── Data Models ─────────────────────────────────────────────────────────
@dataclass
class Tweet:
    id: str
    text: str
    author: str
    author_handle: str
    url: str
    timestamp: str
    views: int
    likes: int
    retweets: int
    replies: int
    quotes: int
    engagement_score: float
    category: str
    query_used: str
    scraped_at: str

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Scraper Core ────────────────────────────────────────────────────────
class XScraper:
    def __init__(self, profile_dir: Path = PROFILE_DIR, headless: bool = HEADLESS):
        self.profile_dir = profile_dir
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
            viewport={"width": 1280, "height": 720},
        )
        self.page = await self.browser.new_page()
        # Stealth
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

    async def close(self):
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()

    async def search(self, query: str, max_tweets: int = 50) -> List[Dict]:
        """Search X.com and return raw tweet data."""
        search_url = f"https://x.com/search?q={query}&src=typed_query&f=live"
        await self.page.goto(search_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        await self.page.wait_for_timeout(3000)

        tweets = []
        seen_ids = set()

        for round_num in range(SCROLL_ROUNDS):
            # Wait for tweets to load
            try:
                await self.page.wait_for_selector('[data-testid="tweet"]', timeout=WAIT_TIMEOUT)
            except:
                break

            tweet_elements = await self.page.query_selector_all('[data-testid="tweet"]')

            for el in tweet_elements:
                try:
                    tweet_data = await self._extract_tweet(el)
                    if tweet_data and tweet_data["id"] not in seen_ids:
                        seen_ids.add(tweet_data["id"])
                        tweets.append(tweet_data)
                        if len(tweets) >= max_tweets:
                            return tweets
                except Exception as e:
                    continue

            # Scroll for more
            await self.page.mouse.wheel(0, 2000)
            await self.page.wait_for_timeout(3000)

        return tweets

    async def _extract_tweet(self, element) -> Optional[Dict]:
        """Extract structured data from tweet element."""
        try:
            # Tweet ID from link
            link_el = await element.query_selector('a[href*="/status/"]')
            if not link_el:
                return None
            href = await link_el.get_attribute("href")
            tweet_id = href.split("/status/")[-1].split("?")[0].split("/")[0]

            # Text content
            text_el = await element.query_selector('[data-testid="tweetText"]')
            text = await text_el.inner_text() if text_el else ""

            # Author
            author_link = await element.query_selector('[data-testid="User-Name"] a')
            author_handle = ""
            author_name = ""
            if author_link:
                href = await author_link.get_attribute("href")
                author_handle = href.split("/")[-1] if href else ""
                author_name = await author_link.inner_text()

            # Timestamp
            time_el = await element.query_selector('time')
            timestamp = await time_el.get_attribute("datetime") if time_el else ""

            # Engagement metrics
            metrics = await self._extract_metrics(element)

            # URL
            url = f"https://x.com/{author_handle}/status/{tweet_id}" if author_handle else f"https://x.com/i/status/{tweet_id}"

            return {
                "id": tweet_id,
                "text": text,
                "author": author_name,
                "author_handle": author_handle,
                "url": url,
                "timestamp": timestamp,
                "metrics": metrics,
            }
        except Exception:
            return None

    async def _extract_metrics(self, element) -> Dict[str, int]:
        """Extract engagement metrics from tweet."""
        metrics = {"views": 0, "likes": 0, "retweets": 0, "replies": 0, "quotes": 0}

        # Views (analytics)
        try:
            views_el = await element.query_selector('[data-testid="analytics"]')
            if views_el:
                views_text = await views_el.inner_text()
                metrics["views"] = self._parse_count(views_text)
        except:
            pass

        # Likes, retweets, replies from buttons
        for action, testid in [
            ("replies", "reply"),
            ("retweets", "retweet"),
            ("likes", "like"),
        ]:
            try:
                btn = await element.query_selector(f'[data-testid="{testid}"]')
                if btn:
                    # Try aria-label first
                    aria = await btn.get_attribute("aria-label")
                    if aria:
                        metrics[action] = self._parse_count(aria)
                    else:
                        # Fallback to inner text
                        txt = await btn.inner_text()
                        metrics[action] = self._parse_count(txt)
            except:
                pass

        return metrics

    @staticmethod
    def _parse_count(text: str) -> int:
        """Parse count from text like '1.2K', '5M', '42'."""
        if not text:
            return 0
        text = text.replace(",", "").strip().upper()
        try:
            if "K" in text:
                return int(float(text.replace("K", "")) * 1000)
            elif "M" in text:
                return int(float(text.replace("M", "")) * 1_000_000)
            else:
                # Extract first number
                match = re.search(r"[\d.]+", text)
                return int(float(match.group())) if match else 0
        except:
            return 0


# ─── Pipeline Functions ──────────────────────────────────────────────────
def calculate_engagement_score(metrics: Dict[str, int]) -> float:
    """Calculate weighted engagement score."""
    score = 0.0
    for metric, weight in ENGAGEMENT_WEIGHTS.items():
        score += metrics.get(metric, 0) * weight
    return round(score, 2)


def is_fresh(timestamp_str: str, max_hours: int = MAX_AGE_HOURS) -> bool:
    """Check if tweet is within max_age_hours."""
    if not timestamp_str:
        return True  # Assume fresh if no timestamp
    try:
        tweet_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        age = datetime.now(tweet_time.tzinfo) - tweet_time
        return age < timedelta(hours=max_hours)
    except:
        return True


def filter_tweets(raw_tweets: List[Dict], category: str, query: str) -> List[Tweet]:
    """Filter and convert raw tweets to Tweet objects."""
    filtered = []
    for rt in raw_tweets:
        if not rt.get("text") or len(rt["text"]) < 20:
            continue
        if not is_fresh(rt.get("timestamp")):
            continue

        metrics = rt.get("metrics", {})
        score = calculate_engagement_score(metrics)
        if score < MIN_ENGAGEMENT_SCORE:
            continue

        tweet = Tweet(
            id=rt["id"],
            text=rt["text"],
            author=rt["author"],
            author_handle=rt["author_handle"],
            url=rt["url"],
            timestamp=rt.get("timestamp", ""),
            views=metrics.get("views", 0),
            likes=metrics.get("likes", 0),
            retweets=metrics.get("retweets", 0),
            replies=metrics.get("replies", 0),
            quotes=metrics.get("quotes", 0),
            engagement_score=score,
            category=category,
            query_used=query,
            scraped_at=datetime.utcnow().isoformat() + "Z",
        )
        filtered.append(tweet)
    return filtered


async def scrape_category(category: str, queries: List[str], max_per_query: int = 30) -> List[Tweet]:
    """Scrape all queries for a category."""
    all_tweets = []
    seen_ids = set()

    async with XScraper() as scraper:
        for query in queries:
            print(f"  🔍 Query: {query}")
            raw = await scraper.search(query, max_tweets=max_per_query)
            filtered = filter_tweets(raw, category, query)
            for t in filtered:
                if t.id not in seen_ids:
                    seen_ids.add(t.id)
                    all_tweets.append(t)
            print(f"    → {len(filtered)} tweets passed filters")
            await asyncio.sleep(3)  # Rate limit

    # Sort by engagement score descending
    all_tweets.sort(key=lambda x: x.engagement_score, reverse=True)
    return all_tweets


async def scrape_all_categories() -> Dict[str, List[Tweet]]:
    """Scrape all categories."""
    results = {}
    for category, queries in CATEGORY_QUERIES.items():
        print(f"\n📂 Category: {category}")
        try:
            tweets = await scrape_category(category, queries)
            results[category] = tweets
            print(f"  ✅ Total: {len(tweets)} tweets")
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results[category] = []
    return results


# ─── Main / CLI ──────────────────────────────────────────────────────────
async def main():
    print("🚀 Starting X.com News Scraper")
    print(f"📁 Profile: {PROFILE_DIR}")
    print(f"🎯 Categories: {list(CATEGORY_QUERIES.keys())}")
    print()

    results = await scrape_all_categories()

    # Summary
    total = sum(len(t) for t in results.values())
    print(f"\n📊 SUMMARY: {total} total tweets across {len(results)} categories")
    for cat, tweets in results.items():
        if tweets:
            top = tweets[0]
            print(f"  {cat}: {len(tweets)} tweets | Top: {top.engagement_score} ({top.author_handle})")

    # Save JSON
    output = {
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "categories": {
            cat: [t.to_dict() for t in tweets]
            for cat, tweets in results.items()
        }
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "x_news_latest.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\n💾 Saved to {out_path}")

    return results


if __name__ == "__main__":
    asyncio.run(main())