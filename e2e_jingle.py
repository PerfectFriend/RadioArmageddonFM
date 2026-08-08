#!/usr/bin/env python
"""Full E2E test: jingle workflow (ACE-Step music + Voicebox voice + ffmpeg mix)."""
import sys
sys.path.insert(0, r"C:\Users\yusya\AI-Radio")
from radio_gen import wf_jingle
import argparse, shutil, tempfile, time
from pathlib import Path

args = argparse.Namespace(
    wf="jingle",
    text=None,
    voice_text="Вы слушаете КриптоИнквизицию! Радио новой цифровой эпохи.",
    prompt=None,
    style="dark psychedelic full-on trance, 148 bpm",
    bed_volume=0.22,
    out=Path(r"C:\Users\yusya\AI-Radio\out\jingle_cryptoinquisition.mp3"),
    seed=424242,
    profile=None,
    keep_tmp=False,
    tmp=Path(tempfile.mkdtemp(prefix="radio-jingle-")),
)
t0 = time.time()
out = wf_jingle(args)
dt = time.time() - t0
print(f"\n=== JINGLE DONE: {out} in {dt:.1f}s ===")
if not args.keep_tmp:
    shutil.rmtree(args.tmp, ignore_errors=True)
