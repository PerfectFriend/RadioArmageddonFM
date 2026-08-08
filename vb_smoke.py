#!/usr/bin/env python
"""Voicebox: create preset profile + generate RU speech smoke test."""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:7860"


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        raw = r.read()
        try:
            return json.loads(raw)
        except Exception:
            return raw.decode()


# 1. create preset profile (Kokoro, ru female voice)
prof = call("POST", "/profiles", {
    "name": "DJ CryptoRadio RU",
    "language": "ru",
    "voice_type": "preset",
    "preset_engine": "kokoro",
    "preset_voice_id": "af_bella",  # ru-capable female
})
print("profile:", json.dumps(prof, ensure_ascii=False)[:400])
pid = prof.get("id") or prof.get("profile_id")
if not pid:
    raise SystemExit("no profile id")

# 2. generate speech
gen = call("POST", "/generate", {
    "profile_id": pid,
    "text": "Вы слушаете КриптоИнквизицию — радио новой цифровой эпохи. Прогноз погоды: в Москве сегодня плюс двадцать два, ясно.",
    "language": "ru",
    "engine": "kokoro",
    "model_size": "0.6B",
})
print("gen:", json.dumps(gen, ensure_ascii=False)[:500])
gid = gen.get("generation_id") or gen.get("id")
if not gid:
    raise SystemExit("no generation id")

# 3. poll status
for i in range(60):
    time.sleep(2)
    st = call("GET", f"/generate/{gid}/status")
    status = st.get("status")
    print(f"poll {i*2}s: {json.dumps(st, ensure_ascii=False)[:300]}")
    if status in ("completed", "done", "success"):
        break
    if status in ("failed", "error"):
        raise SystemExit(f"FAILED: {st}")
