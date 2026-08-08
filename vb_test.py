#!/usr/bin/env python
"""First Voicebox TTS smoke test."""
import json
import urllib.request

body = {"text": "Вы слушаете КриптоИнквизицию — радио новой цифровой эпохи.",
        "language": "ru", "engine": "kokoro"}
req = urllib.request.Request("http://127.0.0.1:7860/generate",
    data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        print(r.status)
        print(r.read().decode()[:1200])
except Exception as e:
    print("ERR", e)
    try:
        print(e.read().decode()[:800])
    except Exception:
        pass
