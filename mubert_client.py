#!/usr/bin/env python3
"""
Mubert API Client for Radio ArmsgeddonFM
Generates royalty-free background music for 24/7 radio stream.
"""

import os
import json
import time
import requests
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

# ─── Config ──────────────────────────────────────────────────────────────
MUBERT_BASE_URL = "https://music-api.mubert.com/api/v3/public"
MUSIC_DIR = Path(r"C:\Users\tomas\ai-radio\music")
BACKGROUND_DIR = MUSIC_DIR / "background"
BACKGROUND_DIR.mkdir(parents=True, exist_ok=True)

# Load credentials from environment or .env
CUSTOMER_ID = os.getenv("MUBERT_CUSTOMER_ID") or os.getenv("MUBERT_API_KEY")
ACCESS_TOKEN = os.getenv("MUBERT_ACCESS_TOKEN")

HEADERS = {
    "customer-id": CUSTOMER_ID,
    "access-token": ACCESS_TOKEN,
    "Content-Type": "application/json",
}

# ─── Genre/Mood mapping for radio ────────────────────────────────────────
RADIO_PRESETS = {
    "night_ambient": {"playlist_index": "1.0.0", "intensity": "low", "mode": "track"},
    "day_chill": {"playlist_index": "2.0.0", "intensity": "medium", "mode": "track"},
    "morning_energy": {"playlist_index": "3.0.0", "intensity": "high", "mode": "track"},
    "late_night": {"playlist_index": "4.0.0", "intensity": "low", "mode": "track"},
    "streaming_ambient": {"playlist_index": "1.0.0", "intensity": "medium", "mode": "streaming"},
    "streaming_chill": {"playlist_index": "2.0.0", "intensity": "medium", "mode": "streaming"},
}

# ─── Data Models ─────────────────────────────────────────────────────────
@dataclass
class MubertTrack:
    track_id: str
    download_url: str
    duration: int
    format: str
    bitrate: int
    playlist_index: str

    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "download_url": self.download_url,
            "duration": self.duration,
            "format": self.format,
            "bitrate": self.bitrate,
            "playlist_index": self.playlist_index,
        }


# ─── Mubert Client ───────────────────────────────────────────────────────
class MubertClient:
    def __init__(self, customer_id: str = None, access_token: str = None):
        self.customer_id = customer_id or CUSTOMER_ID
        self.access_token = access_token or ACCESS_TOKEN
        self.session = requests.Session()
        self.session.headers.update({
            "customer-id": self.customer_id,
            "access-token": self.access_token,
            "Content-Type": "application/json",
        })

    def _check_creds(self):
        if not self.customer_id or not self.access_token:
            raise ValueError("MUBERT_CUSTOMER_ID and MUBERT_ACCESS_TOKEN must be set")

    def generate_track(
        self,
        playlist_index: str = "1.0.0",
        duration: int = 300,
        bitrate: int = 128,
        format: str = "mp3",
        intensity: str = "medium",
        mode: str = "track",
        **kwargs
    ) -> MubertTrack:
        """Generate a single track."""
        self._check_creds()

        payload = {
            "playlist_index": playlist_index,
            "duration": duration,
            "bitrate": bitrate,
            "format": format,
            "intensity": intensity,
            "mode": mode,
        }
        payload.update(kwargs)

        resp = self.session.post(
            f"{MUBERT_BASE_URL}/tracks",
            json=payload,
            timeout=60
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != 200:
            raise Exception(f"Mubert error: {data.get('message', data)}")

        track_data = data["data"]
        return MubertTrack(
            track_id=track_data["track_id"],
            download_url=track_data["download_url"],
            duration=track_data.get("duration", duration),
            format=track_data.get("format", format),
            bitrate=track_data.get("bitrate", bitrate),
            playlist_index=playlist_index,
        )

    def get_streaming_link(
        self,
        playlist_index: str = "1.0.0",
        bitrate: int = 128,
        intensity: str = "medium",
        stream_type: str = "http"
    ) -> str:
        """Get streaming URL for infinite radio stream."""
        self._check_creds()

        params = {
            "playlist_index": playlist_index,
            "bitrate": bitrate,
            "intensity": intensity,
            "type": stream_type,
        }

        resp = self.session.get(
            f"{MUBERT_BASE_URL}/streaming/get-link",
            params=params,
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != 200:
            raise Exception(f"Mubert streaming error: {data.get('message', data)}")

        return data["data"]["stream_url"]

    def download_track(self, track: MubertTrack, output_path: Path = None) -> Path:
        """Download track to local file."""
        if output_path is None:
            timestamp = int(time.time())
            output_path = BACKGROUND_DIR / f"mubert_{track.playlist_index}_{timestamp}.{track.format}"

        resp = requests.get(track.download_url, stream=True, timeout=60)
        resp.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        return output_path

    def generate_and_download(
        self,
        preset: str = "night_ambient",
        duration: int = 3600,
        **kwargs
    ) -> Path:
        """Generate and download track using preset."""
        preset_config = RADIO_PRESETS.get(preset, RADIO_PRESETS["night_ambient"])
        config = {**preset_config, **kwargs, "duration": duration}

        track = self.generate_track(**config)
        return self.download_track(track)


# ─── Radio Music Manager ─────────────────────────────────────────────────
class RadioMusicManager:
    """Manages background music rotation for 24/7 radio."""

    def __init__(self, client: MubertClient):
        self.client = client
        self.current_track: Optional[Path] = None

    def get_preset_for_hour(self, hour: int) -> str:
        """Select preset based on time of day."""
        if 6 <= hour < 10:
            return "morning_energy"
        elif 10 <= hour < 18:
            return "day_chill"
        elif 18 <= hour < 23:
            return "streaming_chill"
        else:
            return "night_ambient"

    def ensure_background_track(self, max_age_hours: int = 4) -> Path:
        """Ensure we have a fresh background track."""
        from datetime import datetime, timedelta

        now = datetime.now()
        hour = now.hour
        preset = self.get_preset_for_hour(hour)

        # Check if current track is fresh enough
        if self.current_track and self.current_track.exists():
            mtime = datetime.fromtimestamp(self.current_track.stat().st_mtime)
            if now - mtime < timedelta(hours=max_age_hours):
                return self.current_track

        # Generate new track
        print(f"🎵 Generating new background track: {preset}")
        track_path = self.client.generate_and_download(
            preset=preset,
            duration=3600,  # 1 hour
        )
        self.current_track = track_path
        print(f"✅ Saved: {track_path}")
        return track_path


# ─── CLI / Testing ───────────────────────────────────────────────────────
def main():
    import sys

    if not CUSTOMER_ID or not ACCESS_TOKEN:
        print("❌ Set MUBERT_CUSTOMER_ID and MUBERT_ACCESS_TOKEN environment variables")
        print("   Get them from https://mubert.com/api after signing up")
        sys.exit(1)

    client = MubertClient()
    manager = RadioMusicManager(client)

    # Test: generate 1-hour background track
    print("🎵 Testing Mubert API...")
    try:
        track_path = manager.ensure_background_track()
        print(f"✅ Generated: {track_path}")
        print(f"   Size: {track_path.stat().st_size / 1024 / 1024:.1f} MB")

        # Test streaming link
        stream_url = client.get_streaming_link(playlist_index="1.0.0", bitrate=128)
        print(f"🔗 Streaming URL: {stream_url[:80]}...")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()