#!/usr/bin/env python
"""Voicebox: fetch generation audio file."""
import json
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


# full generation record
g = call("GET", f"/generate/{GID}")
print("GEN:", json.dumps(g, ensure_ascii=False)[:800])
