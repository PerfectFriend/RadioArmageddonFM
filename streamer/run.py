#!/usr/bin/env python3
"""Streamer - reads playlist and streams to Icecast/SHOUTcast."""
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

import time
import yaml
import json
import subprocess
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["radio"]

def run_streamer():
    """Start streaming from playlist."""
    config = load_config()
    paths = config["paths"]
    
    playlist_file = Path(paths.get("radio_output", "radio_output")) / "playlist.json"
    if not playlist_file.exists():
        print("  ⚠️  No playlist.json found, waiting...")
        return
    
    with open(playlist_file, "r") as f:
        data = json.load(f)
    
    segments = data.get("segments", [])
    if not segments:
        print("  ⚠️  Empty playlist")
        return
    
    print(f"  🎵 Streaming {len(segments)} segments to Icecast...")
    
    # Build concat file for ffmpeg
    concat_file = Path(paths.get("radio_output", "radio_output")) / "concat.txt"
    with open(concat_file, "w") as f:
        for seg in segments:
            f.write(f"file '{seg['file']}'\n")
    
    # FFmpeg to Icecast (placeholder - needs Icecast server config)
    icecast_host = config.get("icecast", {}).get("host", "localhost")
    icecast_port = config.get("icecast", {}).get("port", 8000)
    icecast_mount = config.get("icecast", {}).get("mount", "/radio")
    icecast_password = config.get("icecast", {}).get("password", "hackme")
    
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-re", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:a", "libmp3lame", "-b:a", f"{config['bitrate']}k",
        "-f", "mp3",
        f"icecast://source:{icecast_password}@{icecast_host}:{icecast_port}{icecast_mount}"
    ]
    
    print(f"  📡 ffmpeg -> icecast://{icecast_host}:{icecast_port}{icecast_mount}")
    print("  (Icecast server must be running separately)")
    
    # This would run continuously
    # subprocess.run(cmd)

if __name__ == "__main__":
    print("📡 Streamer starting...")
    print("   Reads playlist.json, streams to Icecast")
    print("   (Icecast server required - not included)")
    
    run_streamer()
    
    # In production, this would loop and reconnect
    while True:
        time.sleep(60)
        run_streamer()