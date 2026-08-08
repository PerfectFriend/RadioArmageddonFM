#!/usr/bin/env python
"""Check query_result response shape."""
import json
import urllib.request

BASE = "http://127.0.0.1:8001"
tid = "eb72db1d-3aee-4968-b9d9-a402a62dcb4b"
q = urllib.request.Request(
    f"{BASE}/query_result",
    data=json.dumps({"task_id_list": json.dumps([tid])}).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(q, timeout=30) as resp:
    raw = resp.read().decode()
print("RAW:", raw[:800])
