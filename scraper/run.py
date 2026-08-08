#!/usr/bin/env python3
"""News Scraper daemon - runs hourly to refresh news feed."""
import sys
sys.path.insert(0, str(Path(__file__).parent))

from news_scraper_production import main
import time
import schedule

def run_scraper():
    """Wrapper to run scraper."""
    print(f"\n⏰ Scheduled scraper run at {time.strftime('%H:%M:%S')}")
    main()

if __name__ == "__main__":
    from pathlib import Path
    
    print("📡 News Scraper Daemon starting...")
    print("   Runs every hour at minute 0")
    
    # Run once immediately
    run_scraper()
    
    # Schedule hourly
    schedule.every().hour.at(":00").do(run_scraper)
    
    while True:
        schedule.run_pending()
        time.sleep(30)