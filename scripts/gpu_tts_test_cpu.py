# -*- coding: utf-8 -*-
"""Тест Qwen3-TTS Base 0.6B на CPU (fp32) — работает стабильно.
Загружает модель Base 0.6B, берёт reference-audio (клон голоса Мастера)
и синтезирует фразу. Работает на CPU, память полностью освобождается после завершения.
"""

import sys
import os

# Force tts-dml-env's site-packages to be first in path (avoid conflicts with Hermes venv)
# MUST be done BEFORE importing torch/transformers
os.environ["PYTHONPATH"] = ""
os.environ["VIRTUAL_ENV"] = ""

# Remove ALL paths that are NOT tts-dml-env or standard library
dml_site = r"C:\Users\tomas\tts-dml-env\Lib\site-packages"
dml_env = r"C:\Users\tomas\tts-dml-env"

# Keep only: tts-dml-env, tts-dml-env/Lib/site-packages, python standard library
new_path = []
for p in sys.path:
    pl = p.lower()
    # Keep standard library paths (no site-packages, no hermes, no appdata hermes)
    if ('site-packages' not in pl and 'hermes' not in pl and 'appdata' not in pl) or pl.endswith('lib') or pl.endswith('dlls') or 'python' in pl:
        new_path.append(p)
    # Keep tts-dml-env paths
    elif dml_env.lower() in pl:
        new_path.append(p)

# Ensure tts-dml-env site-packages is FIRST
if dml_site in new_path:
    new_path.remove(dml_site)
new_path.insert(0, dml_site)

sys.path = new_path
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import time
import glob
import numpy as np
import torch

# текст: если аргумент начинается с @ — читаем из файла (UTF-8)
_text_arg = sys.argv[2] if len(sys.argv) > 2 else "Привет, Мастер! Это тест голоса на CPU."
if _text_arg.startswith("@"):
    try:
        with open(_text_arg[1:], "r", encoding="utf-8") as f:
            TEXT = f.read().strip()
    except Exception as e:
        print(f"[load] ошибка чтения текста из файла: {e}", file=sys.stderr)
        sys.exit(1)
else:
    TEXT = _text_arg
REF_AUDIO = sys.argv[1] if len(sys.argv) > 1 else None


def main():
    print("[CPU] Using CPU for inference (Qwen3-TTS 0.6B Base)", flush=True)

    from qwen_tts.inference.qwen3_tts_model import Qwen3TTSModel

    # Model directory for 0.6B Base
    MODEL_DIR = glob.glob(os.path.expanduser(
        "~/.cache/huggingface/hub/models--Qwen--Qwen3-TTS-12Hz-0.6B-Base/snapshots/*"
    ))[0]

    t0 = time.time()
    print(f"[load] Загружаю модель Base 0.6B (fp32, CPU)...", flush=True)
    tts = Qwen3TTSModel.from_pretrained(
        MODEL_DIR,
        low_cpu_mem_usage=True,
    )
    # Model stays on CPU (fp32)
    import gc
    gc.collect()
    print(f"[load] модель готова за {time.time()-t0:.1f}s", flush=True)

    # reference audio для клона голоса
    if REF_AUDIO:
        print(f"[clone] Reference: {REF_AUDIO}", flush=True)
        prompts = tts.create_voice_clone_prompt(
            ref_audio=REF_AUDIO,
            ref_text="",
            x_vector_only_mode=True,  # только тембр, без текста-референса
        )
    else:
        prompts = None

    t1 = time.time()
    print(f"[synth] Синтез: {TEXT[:60]}...", flush=True)
    wavs, sr = tts.generate_voice_clone(
        text=TEXT,
        language="russian",
        voice_clone_prompt=prompts,
        do_sample=True,
        top_k=50,
        top_p=0.9,
        temperature=0.8,
        repetition_penalty=1.0,
        max_new_tokens=2048,
    )
    print(f"[synth] готово за {time.time()-t1:.1f}s, sr={sr}", flush=True)

    out = os.path.join(os.path.dirname(__file__), "..", "gpu_tts_test.wav")
    import soundfile as sf
    sf.write(out, wavs[0], sr)
    print(f"[ok] {out} ({len(wavs[0])/sr:.1f}s аудио)", flush=True)


if __name__ == "__main__":
    main()