#!/usr/bin/env python3
"""Stream Scheduler - builds hourly playlist from news cache + music."""
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import time
import schedule
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["radio"]

def build_playlist():
    """Build hour playlist from available cache."""
    config = load_config()
    paths = config["paths"]
    
    cache_music = Path(paths["music_dir"])
    cache_news = Path(paths["news_dir"])
    cache_ads = Path(paths["ads_dir"])
    cache_jingles = Path(paths["jingles_dir"])
    out_dir = Path(paths.get("radio_output", "radio_output"))
    out_dir.mkdir(parents=True, exist_ok=True)
    
    playlist = []
    
    # Add jingle
    jingles = list(cache_jingles.glob("**/*.mp3"))
    if jingles:
        playlist.append({"type": "jingle", "file": str(jingles[0])})
    
    # Add music tracks
    for style_dir in cache_music.iterdir():
        if style_dir.is_dir():
            tracks = list(style_dir.glob("*.mp3"))
            if tracks:
                playlist.append({"type": "music", "file": str(tracks[0]), "style": style_dir.name})
    
    # Add news
    for cat_dir in cache_news.iterdir():
        if cat_dir.is_dir():
            news = list(cat_dir.glob("*.mp3"))
            if news:
                playlist.append({"type": "news", "file": str(news[0]), "category": cat_dir.name})
    
    # Add ads
    ads = list(cache_ads.glob("*.mp3"))
    if ads:
        playlist.append({"type": "ad", "file": str(ads[0])})
    
    # Save playlist
    import json
    playlist_file = out_dir / "playlist.json"
    playlist_file.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "segments": playlist
    }, indent=2))
    
    print(f"📋 Playlist built: {len(playlist)} segments -> {playlist_file}")

def run_scheduler():
    """Wrapper to run scheduler."""
    print(f"\n⏰ Scheduled playlist build at {time.strftime('%H:%M:%S')}")
    build_playlist()

if __name__ == "__main__":
    print("📋 Stream Scheduler starting...")
    print("   Builds playlist every hour at minute 5")
    
    run_scheduler()
    
    import schedule
    schedule.every().hour.at(":05").do(run_scheduler)
    
    while True:
        schedule.run_pending()
        time.sleep(30)