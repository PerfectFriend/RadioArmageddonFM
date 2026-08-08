# RadioArmageddonFM — Architecture for Integration

This document describes the expected interfaces for components you'll push from the other machine.

---

## Component Overview

```
┌─────────────────┐     ┌──────────────┐     ┌────────────────┐     ┌──────────────┐
│   News Scraper  │────▶│   Text Buffer │────▶│  Stream Builder │────▶│  Icecast/    │
│  (your code)    │     │  (your code)  │     │  (radio_gen)   │     │  SHOUTcast   │
└─────────────────┘     └──────────────┘     └────────────────┘     └──────────────┘
        │                      │                      │
        │ Text summaries       │ Ranked/selected      │ MP3 segments
        │ + metadata           │ audio segments       │ + playlist
        ▼                      ▼                      ▼
   scraper/               buffer/               scheduler/
```

---

## 1. News Scraper Interface (`scraper/`)

**Expected output:** JSONL lines appended to `buffer/incoming.jsonl`

```json
{
  "id": "uuid-v4",
  "source": "coindesk|twitter|rss|telegram",
  "title": "Bitcoin hits $100k",
  "summary": "Bitcoin reached $100,000 for the first time...",
  "full_text": "...",           // optional
  "url": "https://...",
  "published_at": "2026-08-08T12:00:00Z",
  "tags": ["btc", "ath", "market"],
  "priority": 8,                // 1-10, higher = more urgent
  "lang": "en|ru|es",
  "scraped_at": "2026-08-08T12:01:00Z"
}
```

**Requirements:**
- Append-only to `buffer/incoming.jsonl` (one line per item)
- Deduplication by `id` or `url` (your side)
- Runs as daemon/cron, not blocking

---

## 2. Text Buffer / Selector (`buffer/`)

**Input:** `buffer/incoming.jsonl` (from scraper)
**Output:** `buffer/selected.jsonl` (items ready for TTS)

```json
{
  "id": "uuid-v4",
  "source_item_id": "uuid-from-scraper",
  "text_for_tts": "Bitcoin reached one hundred thousand dollars...",
  "lang": "ru",
  "priority": 8,
  "category": "news|forecast|ad|jingle",
  "style_hint": "dark psytrance 148bpm",
  "max_duration_sec": 30,
  "selected_at": "2026-08-08T12:02:00Z"
}
```

**Buffer responsibilities:**
- Dedupe / filter by priority / time window
- Rewrite summaries for TTS (numbers→words, abbreviations, pronunciation hints)
- Assign `style_hint` matching current radio block genre
- Rank & select top-N for next hour
- Mark processed items (move to `buffer/archive/`)

---

## 3. Stream Scheduler / Builder (`scheduler/`)

**Input:** `buffer/selected.jsonl`
**Output:** `stream/playlist.m3u` + segment MP3s in `stream/segments/`

**Flow:**
1. Read selected items
2. For each: call `radio_gen.py` workflow (newsfeed/forecast/ad/jingle) with `--style` from `style_hint`
3. Generate MP3 segments via ACE-Step + Voicebox + ffmpeg
4. Build playlist (m3u or JSON) with timing metadata
5. Handle transitions / crossfades / filler music

**Playlist format (JSON):**
```json
{
  "generated_at": "2026-08-08T12:05:00Z",
  "valid_until": "2026-08-08T13:05:00Z",
  "segments": [
    {"file": "segments/news_001.mp3", "duration": 28.5, "type": "newsfeed", "title": "BTC ATH"},
    {"file": "segments/jingle_001.mp3", "duration": 8.0, "type": "jingle"},
    {"file": "segments/ad_001.mp3", "duration": 20.0, "type": "ad"},
    {"file": "segments/music_001.mp3", "duration": 240.0, "type": "music", "prompt": "dark psytrance..."}
  ]
}
```

---

## 4. Streamer / Icecast Source (`streamer/`)

**Input:** `stream/playlist.json` + `stream/segments/*.mp3`
**Output:** Live audio stream to Icecast/SHOUTcast

**Responsibilities:**
- Read playlist sequentially
- Stream MP3 frames to Icecast source port
- Handle schedule rollover (load new playlist hourly)
- Gapless playback / crossfade between segments
- Metadata injection (ICY title update per segment)
- Health monitoring / auto-reconnect

---

## Integration Points (what radio_gen.py provides)

```python
# In radio_gen.py - you can import and use directly:
from radio_gen import wf_newsfeed, wf_forecast, wf_ad, wf_jingle
import argparse
from pathlib import Path

# Example: generate a news segment
args = argparse.Namespace(
    wf="newsfeed",
    text=None,
    voice_text="Bitcoin reached one hundred thousand dollars...",
    prompt=None,
    style="dark psytrance 148bpm",      # from buffer's style_hint
    bed_volume=0.22,
    out=Path("stream/segments/news_001.mp3"),
    seed=12345,
    profile=None,
    keep_tmp=False,
    tmp=Path(tempfile.mkdtemp(prefix="radio-news-")),
)
wf_newsfeed(args)  # returns Path to generated MP3
```

---

## Directory Structure (after your push)

```
RadioArmageddonFM/
├── radio_gen.py              # Core audio generation (already here)
├── start.py                  # Quick launcher
├── scraper/                  # YOUR CODE - news fetching + summarization
│   ├── __init__.py
│   ├── sources/              # RSS, Twitter, Telegram, API adapters
│   ├── summarizer.py         # LLM-based summary → TTS text
│   └── run.py                # Daemon entry point
├── buffer/                   # YOUR CODE - selection & ranking
│   ├── __init__.py
│   ├── incoming.jsonl        # Scraper writes here
│   ├── selected.jsonl        # Buffer writes here
│   ├── archive/              # Processed items
│   └── run.py                # Selector daemon
├── scheduler/                # YOUR CODE - playlist builder
│   ├── __init__.py
│   ├── builder.py            # Calls radio_gen, builds playlist
│   └── run.py                # Hourly daemon
├── streamer/                 # YOUR CODE - Icecast source
│   ├── __init__.py
│   ├── source.py             # MP3 → Icecast streaming
│   └── run.py                # Stream daemon
├── stream/                   # Runtime artifacts (gitignored)
│   ├── playlist.json
│   └── segments/
├── out/                      # Demo outputs (gitignored)
├── tests/
└── README*.md
```

---

## Quick Integration Checklist

When you push your code, verify:

- [ ] `scraper/run.py` appends valid JSONL to `buffer/incoming.jsonl`
- [ ] `buffer/run.py` reads incoming, writes `buffer/selected.jsonl`
- [ ] `scheduler/run.py` reads selected, calls `radio_gen.py` workflows, writes `stream/playlist.json`
- [ ] `streamer/run.py` reads playlist, streams to Icecast
- [ ] All daemons handle SIGTERM gracefully (cleanup, flush)
- [ ] Config via env vars (no hardcoded paths)
- [ ] Logs to stdout (structured JSON preferred)

---

## Next Steps

1. Push your `scraper/`, `buffer/`, `scheduler/`, `streamer/` folders
2. I'll review, run integration tests, wire into `start.py` as managed services
3. Add systemd/Windows service configs for production
4. Deploy Icecast + RadioArmageddonFM on target server

---

*This architecture is intentionally decoupled — each component is a replaceable daemon communicating via filesystem (JSONL). Easy to test, debug, and scale.*