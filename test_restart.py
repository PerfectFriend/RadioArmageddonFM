#!/usr/bin/env python
"""Test ace_step_restart: kill dead server state, launch fresh, verify health."""
import sys
sys.path.insert(0, r"C:\Users\yusya\AI-Radio")
from radio_gen import ace_step_restart, ace_step_health, ACE_STEP_URL
import time

print("health before:", ace_step_health())
t0 = time.time()
proc = ace_step_restart(max_wait=150)
dt = time.time() - t0
print(f"restart took {dt:.1f}s, proc={proc}")
print("health after:", ace_step_health())
