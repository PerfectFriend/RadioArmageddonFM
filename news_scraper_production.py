#!/usr/bin/env python3
"""
PRODUCTION NEWS SCRAPER for Radio Pipeline
- Runs hourly via cron
- Parses TOP 100+ RSS feeds
- Saves only NEW items from last hour
- Organizes by topic folders in /newsfeed
- Outputs ready-to-TTS text files
"""

import feedparser
import json
import re
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

# ─── Config ──────────────────────────────────────────────────────────────
NEWSFEED_DIR = Path(r"C:\Users\tomas\ai-radio\newsfeed")
STATE_FILE = NEWSFEED_DIR / ".scraper_state.json"
MAX_AGE_HOURS = 1.5  # Slightly more than 1 hour to catch delays
MAX_WORKERS = 16
TIMEOUT = 15
USER_AGENT = "RadioNewsBot/2.0 (+https://github.com/RadioArmsgeddonFM)"

# Import the feeds
sys.path.insert(0, str(Path(__file__).parent))
from top100_feeds import TOP_100_RSS_FEEDS


# ─── Helpers ─────────────────────────────────────────────────────────────
def load_state() -> Dict:
    """Load last run state (seen item hashes)."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except:
            return {"last_run": None, "seen_hashes": {}}
    return {"last_run": None, "seen_hashes": {}}


def save_state(state: Dict):
    """Save state atomically."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
    tmp.replace(STATE_FILE)


def make_hash(item: Dict) -> str:
    """Create unique hash for deduplication."""
    content = f"{item.get('title','')}|{item.get('url','')}|{item.get('published','')}"
    return hashlib.md5(content.encode()).hexdigest()[:16]


def clean_html(text: str) -> str:
    """Strip HTML tags and clean text."""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def parse_date(entry) -> Optional[datetime]:
    """Parse publication date from feed entry."""
    for field in ['published_parsed', 'updated_parsed']:
        if hasattr(entry, field) and getattr(entry, field):
            try:
                dt = datetime(*getattr(entry, field)[:6], tzinfo=timezone.utc)
                return dt
            except:
                pass
    # Try string parsing
    for field in ['published', 'updated']:
        if hasattr(entry, field) and getattr(entry, field):
            try:
                # feedparser usually returns UTC
                dt = datetime.fromisoformat(getattr(entry, field).replace('Z', '+00:00'))
                return dt
            except:
                pass
    return None


def is_recent(pub_date: Optional[datetime], max_hours: float = 1.5) -> bool:
    """Check if item is within the time window."""
    if not pub_date:
        return True  # Include if no date (better to include)
    now = datetime.now(timezone.utc)
    age = now - pub_date
    return age < timedelta(hours=max_hours)


def get_category_folder(category: str) -> str:
    """Map category to folder name."""
    # Normalize category names
    mapping = {
        'tech': 'tech',
        'ai_ml': 'ai',
        'space': 'space',
        'science': 'science',
        'politics': 'politics',
        'war': 'war',
        'finance': 'finance',
        'crypto': 'crypto',
        'culture': 'culture',
        'gaming': 'gaming',
        'hardware': 'hardware',
        'auto': 'auto',
        'health': 'health',
        'energy': 'energy',
        'ru_tech': 'ru/tech',
        'ru_politics': 'ru/politics',
        'ru_war': 'ru/war',
    }
    return mapping.get(category, category)


# ─── Main Scraper ────────────────────────────────────────────────────────
class RadioNewsScraper:
    def __init__(self):
        self.state = load_state()
        self.new_hashes = {}
        self.stats = {"total": 0, "new": 0, "duplicates": 0, "errors": 0, "by_category": {}}
        # Load feeds
        from top100_feeds import TOP_100_RSS_FEEDS
        self.feeds = TOP_100_RSS_FEEDS

    def fetch_feed(self, url: str, category: str, source: str) -> List[Dict]:
        """Fetch and parse single RSS feed."""
        items = []
        try:
            feed = feedparser.parse(url, request_headers={'User-Agent': 'RadioNewsBot/2.0'})
            if feed.bozo and feed.bozo_exception:
                # Log but continue
                pass

            for entry in feed.entries[:20]:  # Limit per feed
                pub_date = parse_date(entry)
                if not is_recent(pub_date):
                    continue

                title = clean_html(entry.get('title', ''))
                summary = clean_html(entry.get('summary', entry.get('description', '')))
                link = entry.get('link', '')
                guid = entry.get('id', link)

                if not title or not link:
                    continue

                item = {
                    'title': title[:200],
                    'summary': summary[:500],
                    'url': link,
                    'source': feed.feed.get('title', source),
                    'category': category,
                    'published': pub_date.isoformat() if pub_date else datetime.now(timezone.utc).isoformat(),
                    'scraped_at': datetime.now(timezone.utc).isoformat(),
                    'guid': guid,
                }
                items.append(item)

        except Exception as e:
            self.stats['errors'] += 1
            print(f"  ❌ {url}: {e}")

        return items

    def process_category(self, category: str, feeds: Dict[str, str]) -> List[Dict]:
        """Process all feeds for a category."""
        print(f"📂 {category} ({len(feeds)} feeds)")
        all_items = []

        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_source = {
                executor.submit(self.fetch_feed, url, category, source): source
                for source, url in feeds.items()
            }

            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    items = future.result(timeout=20)
                    if items:
                        print(f"  ✅ {source}: {len(items)} items")
                    all_items.extend(items)
                except Exception as e:
                    self.stats['errors'] += 1
                    print(f"  ❌ {source}: {e}")

        # Deduplicate within category
        seen = set()
        unique = []
        for item in all_items:
            h = make_hash(item)
            if h not in seen:
                seen.add(h)
                unique.append(item)

        print(f"  📊 {category}: {len(unique)} unique items")
        self.stats['by_category'][category] = len(unique)
        self.stats['total'] += len(unique)
        return unique

    def save_items(self, items: List[Dict], category: str):
        """Save items as individual text files in category folder."""
        if not items:
            return

        folder = NEWSFEED_DIR / get_category_folder(category)
        folder.mkdir(parents=True, exist_ok=True)

        # Also create/update index.json for the category
        index_file = folder / "index.json"
        existing_index = []
        if index_file.exists():
            try:
                existing_index = json.loads(index_file.read_text(encoding='utf-8'))
            except:
                pass

        # Create a map of existing items by URL for quick lookup
        existing_by_url = {item['url']: item for item in existing_index}

        new_count = 0
        for item in items:
            url = item['url']
            if url in existing_by_url:
                self.stats['duplicates'] += 1
                continue

            # This is a NEW item
            self.stats['new'] += 1

            # Create individual text file for TTS
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            safe_title = re.sub(r'[^\w\s-]', '', item['title'])[:50]
            safe_title = re.sub(r'\s+', '_', safe_title)
            filename = f"{timestamp}_{safe_title}.txt"
            filepath = folder / filename

            # Format for TTS: title + summary
            tts_text = f"{item['title']}. {item['summary']}"
            tts_text = re.sub(r'\s+', ' ', tts_text).strip()

            filepath.write_text(tts_text, encoding='utf-8')

            # Add to index
            existing_by_url[url] = {
                'title': item['title'],
                'summary': item['summary'],
                'url': item['url'],
                'source': item['source'],
                'category': item['category'],
                'published': item['published'],
                'scraped_at': item['scraped_at'],
                'file': filename,
            }

        # Save updated index
        index_file.write_text(
            json.dumps(list(existing_by_url.values()), ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

    def run(self):
        """Main entry point."""
        print("=" * 60)
        print(f"🎙 RADIO NEWS SCRAPER - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"📁 Output: {NEWSFEED_DIR}")
        print(f"📡 Categories: {len(TOP_100_RSS_FEEDS)}")
        total_feeds = sum(len(v) for v in TOP_100_RSS_FEEDS.values())
        print(f"📡 Total feeds: {sum(len(v) for v in TOP_100_RSS_FEEDS.values())}")
        print("=" * 60)

        start_time = datetime.now(timezone.utc)

        # Import feeds
        # from top100_feeds import TOP_100_RSS_FEEDS

        all_new_items = []

        for category, feeds in self.feeds.items():
            try:
                print(f"\n📂 {category}")
                items = self.process_category(category, feeds)
                if items:
                    self.save_items(items, category)
                    all_new_items.extend(items)
            except Exception as e:
                print(f"  ❌ Category {category} failed: {e}")
                self.stats['errors'] += 1

        # Summary
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        print("\n" + "=" * 60)
        print(f"⏱ Completed in {elapsed:.1f}s")
        print(f"📊 Total processed: {self.stats['total']}")
        print(f"🆕 New items saved: {self.stats['new']}")
        print(f"🔄 Duplicates skipped: {self.stats['duplicates']}")
        print(f"❌ Errors: {self.stats['errors']}")
        print(f"📂 By category:")
        for cat, count in sorted(self.stats['by_category'].items(), key=lambda x: -x[1]):
            if count > 0:
                print(f"  {cat}: {count}")

        # Update state
        self.state['last_run'] = datetime.now(timezone.utc).isoformat()
        # Keep only last 10000 hashes to prevent unbounded growth
        if len(self.state['seen_hashes']) > 10000:
            self.state['seen_hashes'] = dict(list(self.state['seen_hashes'].items())[-5000:])
        save_state(self.state)

        return self.stats


def main():
    NEWSFEED_DIR.mkdir(parents=True, exist_ok=True)
    scraper = RadioNewsScraper()
    stats = scraper.run()
    return 0 if stats['errors'] < 10 else 1


if __name__ == "__main__":
    sys.exit(main())