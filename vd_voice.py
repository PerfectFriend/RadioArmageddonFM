#!/usr/bin/env python3
"""Голос джингла с НАСТОЯЩИМИ эмоциями через Qwen3-TTS VoiceDesign + instruct.

Документация Qwen3-TTS: эмоция/тембр задаются natural-language параметром
instruct (generate_voice_design(text, instruct, language)). Здесь — русский.

Текст режем на короткие реплики (один вдох), каждую синтезируем отдельно.
Запуск:  python3 vd_voice.py <emotion> [outdir]
"""
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/vd_voice")
OUT.mkdir(parents=True, exist_ok=True)

# реплики слогана (ADR voicy 0012: без внутренних запятых)
LINES = [
    "Радио Армагеддон ЭФ ЭМ!",
    "Радио на все времена",
    "для тех, кто сел покакать!",
]

# emo -> instruct (тембр диктора + эмоция, по документации Qwen3-TTS)
INSTRUCT = {
    "angry":    "Зрелый мужской голос ведущего радио, низкий баритон, харизматичный. "
                "Говори очень зло и агрессивно, с нажимом на каждом слове, почти криком, "
                "как будто врываешься в эфир",
    "cheerful": "Мужской голос ведущего радио, средний тембр, дружелюбный. "
                "Говори весело и задорно, с широкой улыбкой в голосе, энергично и задорно",
    "calm":     "Мужской голос ведущего радио, низкий баритон, спокойный и уверенный. "
                "Говори медленно, размеренно, расслабленно, как ночью наедине со слушателем",
    "hype":     "Мужской голос ведущего радио, высокий тембр, возбуждённый. "
                "Говори гиперэнергично, на максимуме, с восторгом, как на большом фестивале перед толпой",
}


def main():
    emo = sys.argv[1]
    import torch
    from qwen_tts import Qwen3TTSModel
    t0 = time.time()
    tts = Qwen3TTSModel.from_pretrained(
        "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
        device_map="cpu", dtype=torch.bfloat16,
    )
    print(f"model loaded in {time.time()-t0:.0f}s", flush=True)
    instruct = INSTRUCT[emo]
    parts = []
    for i, line in enumerate(LINES):
        t1 = time.time()
        wavs, sr = tts.generate_voice_design(
            text=line, instruct=instruct, language="Russian",
            max_new_tokens=2048, do_sample=True, top_k=50, top_p=1.0,
            temperature=0.9, repetition_penalty=1.05,
        )
        p = OUT / f"{emo}_{i}.wav"
        sf.write(str(p), wavs[0], sr)
        print(f"  line {i} '{line[:20]}...' -> {p.name} {len(wavs[0])/sr:.1f}s in {time.time()-t1:.0f}s", flush=True)
        parts.append(p)
    # склейка с паузой 0.35с
    import subprocess
    fl = OUT / f"{emo}_concat.txt"
    fl.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    out = OUT / f"{emo}_voice.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(fl), "-af", "apad=pad_dur=0.35", "-c:a", "pcm_s16le",
                    str(out)], check=True)
    print(f"VOICE_DONE {out} total={time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
