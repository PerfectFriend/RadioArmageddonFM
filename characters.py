#!/usr/bin/env python3
"""Характеры дикторов радио с фазовой ротацией настроения.

Идея «сдвига по фазе»: N характеров сидят на эмоциональном круге, каждый
следующий смещён на 360/N градусов (для 4 характеров — по 90°, для 3 — по 120°).
Каждая генерация увеличивает фазу на один шаг, поэтому настроение каждый раз
меняется по кругу, а не повторяется.

Каждый характер = свой reference-голос (клон) + стиль оформления текста:
злой — капс и "!!!", весёлый — эмодзи и "!", спокойный — точки, гипер — "🔥".
"""
import json
import math
import os
from pathlib import Path

# Порядок характеров на круге (углы кратны 360/N)
CHARACTERS = [
    {"name": "angry",    "label": "ЗЛОЙ",     "voice_key": "char_angry",
     "style": lambda t: t.upper() + "!!!"},
    {"name": "cheerful", "label": "ВЕСЁЛЫЙ",  "voice_key": "char_cheerful",
     "style": lambda t: t + "! 😄"},
    {"name": "calm",     "label": "СПОКОЙНЫЙ","voice_key": "char_calm",
     "style": lambda t: t + "..."},
    {"name": "hype",     "label": "ХАЙПОВЫЙ","voice_key": "char_hype",
     "style": lambda t: "🔥 " + t + " 🔥"},
]

STATE_FILE = Path(os.environ.get("RADIO_CHAR_STATE", str(Path.home() / ".w420/radio_char_state.json")))


def phase_step() -> float:
    """Шаг фазы в градусах: 360/N (120° для 3, 90° для 4 характеров)."""
    return 360.0 / len(CHARACTERS)


def current_phase() -> float:
    try:
        return float(json.loads(STATE_FILE.read_text()).get("phase", 0.0))
    except Exception:
        return 0.0


def advance_phase() -> float:
    phase = (current_phase() + phase_step()) % 360.0
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"phase": phase}))
    os.replace(tmp, STATE_FILE)
    return phase


def character_at(phase: float):
    """Характер по углу фазы: индекс = round(phase / step) % N."""
    step = phase_step()
    idx = int(round(phase / step)) % len(CHARACTERS)
    return CHARACTERS[idx]


def pick_character():
    """Следующий характер по фазе + текст со стилем. Возвращает (char, styled_text_fn)."""
    phase = advance_phase()
    ch = character_at(phase)
    return ch, phase


def voice_id_for(key: str, voices: list) -> str:
    for v in voices:
        if v.get("name") == key:
            return v["id"]
    return voices[0]["id"] if voices else ""


if __name__ == "__main__":
    # демо: 4 подряд генерации — фаза 90,180,270,0 → все 4 характера по кругу
    for i in range(4):
        ch, ph = pick_character()
        print(f"phase={ph:6.1f}°  char={ch['label']:10s}  text={ch['style']('Привет, это радио')}")
