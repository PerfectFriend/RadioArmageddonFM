#!/usr/bin/env python
"""Voicebox: poll generation status (raw) + fetch audio."""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:7860"
GID = "dd91972e-20e1-4c4e-8377-358a8eb92489"


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


for i in range(90):
    time.sleep(2)
    st = call("GET", f"/generate/{GID}/status")
    print(f"[{i*2}s] {type(st).__name__}: {json.dumps(st, ensure_ascii=False)[:400]}")
    if isinstance(st, dict):
        s = st.get("status")
        if s == "completed":
            print("DONE:", json.dumps(st, ensure_ascii=False)[:800])
            break
        if s in ("failed", "error"):
            print("FAILED:", st)
            break
    elif isinstance(st, str) and st in ("completed", "done", "success"):
        print("DONE(plain):", st)
        break
