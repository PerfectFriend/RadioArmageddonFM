#!/usr/bin/env python
"""Raw release_task response inspection."""
import json
import urllib.request

BASE = "http://127.0.0.1:8001"
body = {
    "prompt": "energetic radio station jingle, bright synth arpeggio, 8 seconds",
    "audio_duration": 8,
    "inference_steps": 8,
    "audio_format": "mp3",
    "batch_size": 1,
    "thinking": False,
}
req = urllib.request.Request(f"{BASE}/release_task", data=json.dumps(body).encode(),
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        print("status:", r.status)
        raw = r.read()
        print("raw:", raw[:400])
except Exception as e:
    print("ERR:", e)
    try:
        print(e.read().decode()[:400])
    except Exception:
        pass
