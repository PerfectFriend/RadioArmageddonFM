#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPU-TTS CLI для Мастер-ФМ (совместим с voicebox_tts.py интерфейсом).

Reads text from a temp file (arg 1), synthesizes via Qwen3-TTS 1.7B on Radeon 780M
(torch-directml), writes WAV to output path (arg 2).

Usage:
    gpu_tts_cli.py <input_text_path> <output_audio_path>

ENV (optional):
    GPU_TTS_REF_WAV -- path to reference WAV for voice clone
    GPU_TTS_ENV     -- path to venv tts-dml-env
"""

# THIS SCRIPT RUNS IN THE HERMES VENV BUT MUST DELEGATE TO tts-dml-env PYTHON
# The actual GPU TTS logic is in gpu_tts_test.py which handles path isolation
import os
import sys
import subprocess
import shutil
import tempfile

# ---- Настройки по умолчанию (forward slashes - Windows понимает) ----
DEFAULT_REF_WAV = "C:/Users/tomas/Voicebox/data/profiles/ac9a52ff-0c1a-44c3-a378-959542178e06/156c65ec-7000-45cc-858b-daa368340c1a.wav"
DEFAULT_ENV = "C:/Users/tomas/tts-dml-env"
GPU_TTS_SCRIPT = "C:/Users/tomas/ai-radio/scripts/gpu_tts_test.py"


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: gpu_tts_cli.py <input_text_path> <output_path>", file=sys.stderr)
        return 1

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    # Читаем текст из файла (UTF-8)
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            text = f.read().strip()
    except Exception as e:
        print(f"read input failed: {e}", file=sys.stderr)
        return 1

    if not text:
        print("empty text", file=sys.stderr)
        return 1

    # Референс-WAV
    ref_wav = os.environ.get("GPU_TTS_REF_WAV", DEFAULT_REF_WAV)
    if not os.path.exists(ref_wav):
        print(f"ref wav not found: {ref_wav}", file=sys.stderr)
        return 1

    # Путь к venv
    env_path = os.environ.get("GPU_TTS_ENV", DEFAULT_ENV)
    python_exe = os.path.join(env_path, "Scripts", "python.exe")
    if not os.path.exists(python_exe):
        print(f"python not found: {python_exe}", file=sys.stderr)
        return 1

    # Пишем текст во временный файл (Windows Python умеет читать UTF-8 из файла)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", delete=False) as tf:
        tf.write(text)
        text_file = tf.name

    try:
        # Запуск GPU-TTS: передаём путь к файлу с текстом
        env = os.environ.copy()
        env["PYTHONPATH"] = ""
        env["VIRTUAL_ENV"] = ""

        cmd = [python_exe, GPU_TTS_SCRIPT, ref_wav, f"@{text_file}"]

        print(f"[gpu_tts] synth: {text[:60]}...", flush=True)
        try:
            # Таймаут с запасом (длинный текст до 160с + загрузка модели 30с)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
        except subprocess.TimeoutExpired:
            print("[gpu_tts] timeout", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"[gpu_tts] launch failed: {e}", file=sys.stderr)
            return 1

        if result.returncode != 0:
            print(f"[gpu_tts] failed (code {result.returncode}): {result.stderr[-500:]}", file=sys.stderr)
            return 1

        # Ищем выходной файл (скрипт пишет в ai-radio/gpu_tts_test.wav)
        generated = "C:/Users/tomas/ai-radio/gpu_tts_test.wav"
        if not os.path.exists(generated):
            generated = os.path.join(os.path.dirname(GPU_TTS_SCRIPT), "..", "gpu_tts_test.wav")
            generated = os.path.normpath(generated)

        if not os.path.exists(generated) or os.path.getsize(generated) < 1000:
            print(f"[gpu_tts] output not found or empty: {generated}", file=sys.stderr)
            return 1

        # Копируем в запрошенный выходной путь
        try:
            shutil.copy2(generated, output_path)
            print(f"[gpu_tts] ok: wrote {os.path.getsize(output_path)} bytes to {output_path}")
            return 0
        except Exception as e:
            print(f"[gpu_tts] copy failed: {e}", file=sys.stderr)
            return 1
    finally:
        # Удаляем временный файл
        try:
            os.unlink(text_file)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())