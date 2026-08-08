#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Master-FM: НОЧНОЙ БАТЧ (20:00-07:00)
Полная генерация всего контента для кэша:
- Музыка (все стили) через MusicGen DirectML
- Новости (из newsfeed, уже есть) + TTS озвучка
- Рекламные блоки (самореклама) через TTS
- Джинглы (все темы) через TTS
- Аудиокниги (главы) через TTS

Запуск: python scripts/night_batch.py
"""

import os
import sys
import yaml
import time
import random
import subprocess
import tempfile
import shutil
import json
import torch
import torchaudio
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
import logging

# Setup
RADIO_ROOT = r"C:\Users\tomas\ai-radio"
sys.path.insert(0, RADIO_ROOT)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load config
with open(os.path.join(RADIO_ROOT, "config.yaml"), "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)["radio"]

CACHE = os.path.join(RADIO_ROOT, CONFIG["paths"]["cache_root"])
MUSIC_DIR = os.path.join(CACHE, "music")
NEWS_DIR = os.path.join(CACHE, "news")
ADS_DIR = os.path.join(CACHE, "ads")
JINGLES_DIR = os.path.join(CACHE, "jingles")
AUDIOBOOKS_DIR = os.path.join(CACHE, "audiobooks")
NEWSFEED_DIR = Path(r"C:\Users\tomas\ai-radio\newsfeed")

# TTS
GPU_TTS_CLI = os.path.join(RADIO_ROOT, "scripts", "gpu_tts_cli.py")
REF_WAV = "C:/Users/tomas/Voicebox/data/profiles/ac9a52ff-0c1a-44c3-a378-959542178e06/156c65ec-7000-45cc-858b-daa368340c1a.wav"

# Night batch params
NB = CONFIG["modes"]["night_batch"]
MUSIC_PER_STYLE = NB["music_per_style"]
MUSIC_DURATION = NB["music_duration_sec"]
ADS_COUNT = NB["ads_count"]
JINGLES_PER_THEME = NB["jingles_per_theme"]
AUDIOBOOK_CHAPTERS = NB["audiobook_chapters"]

# Ensure cache dirs
for d in [MUSIC_DIR, NEWS_DIR, ADS_DIR, JINGLES_DIR, AUDIOBOOKS_DIR]:
    Path(d).mkdir(parents=True, exist_ok=True)


def synth_via_gpu_tts_cli(text: str, out_path: str) -> bool:
    """Озвучить текст через gpu_tts_cli.py (отдельный процесс, память освобождается)."""
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", delete=False) as tf:
        tf.write(text)
        text_file = tf.name

    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = ""
        env["VIRTUAL_ENV"] = ""
        env["GPU_TTS_REF_WAV"] = REF_WAV

        cmd = [sys.executable, GPU_TTS_CLI, text_file, out_path]

        logger.info(f"[tts] synth: {text[:60]}...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)

        if result.returncode != 0:
            logger.error(f"  ! ошибка синтеза (code {result.returncode}): {result.stderr[-500:]}")
            return False

        ok = os.path.exists(out_path) and os.path.getsize(out_path) > 1000
        if not ok:
            logger.error(f"  ! синтез не удался: файл пустой или не создан")
        else:
            logger.info(f"[tts] ok: wrote {os.path.getsize(out_path)} bytes to {out_path}")
        return ok
    except subprocess.TimeoutExpired:
        logger.error(f"  ! таймаут синтеза (300с)")
        return False
    except Exception as e:
        logger.error(f"  ! ошибка запуска: {e}")
        return False
    finally:
        try:
            os.unlink(text_file)
        except Exception:
            pass


# ============================================================
# 1. МУЗЫКА — генерация через MusicGen DirectML (CPU)
# ============================================================
def generate_music():
    logger.info("=" * 60)
    logger.info("🎵 GENERATING MUSIC")
    logger.info("=" * 60)

    from musicgen_directml import MusicGenDirectML, RADIO_PRESETS

    client = MusicGenDirectML(
        model_path="C:/Users/tomas/ai-radio/models/musicgen-small",
        output_dir="C:/Users/tomas/ai-radio/music_output",
    )

    styles = list(CONFIG["sources"]["music_styles"].keys())
    total_generated = 0

    for style in styles:
        style_dir = os.path.join(MUSIC_DIR, style)
        Path(style_dir).mkdir(parents=True, exist_ok=True)

        # Check existing
        existing = list(Path(style_dir).glob("*.wav"))
        if len(existing) >= MUSIC_PER_STYLE:
            logger.info(f"  {style}: already has {len(existing)} tracks, skipping")
            continue

        need = MUSIC_PER_STYLE - len(existing)
        logger.info(f"  {style}: generating {need} tracks ({MUSIC_DURATION}s each)...")

        preset = RADIO_PRESETS.get("night", RADIO_PRESETS["night"])
        preset["prompt"] = CONFIG["sources"]["music_styles"][style]

        for i in range(need):
            try:
                filename = f"{style}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i:03d}.wav"
                path = client.generate_and_save(
                    filename=filename,
                    prompt=preset["prompt"],
                    duration=MUSIC_DURATION,
                    temperature=preset["temperature"],
                    top_k=preset["top_k"],
                    top_p=preset["top_p"],
                )
                # Move to cache
                target = Path(style_dir) / filename
                path.rename(target)
                total_generated += 1
                logger.info(f"    ✅ {target.name}")
            except Exception as e:
                logger.error(f"    ❌ track {i}: {e}")

    logger.info(f"🎵 Music generation complete: {total_generated} new tracks")


# ============================================================
# 2. НОВОСТИ — берем из newsfeed и озвучиваем TTS
# ============================================================
def generate_news():
    logger.info("=" * 60)
    logger.info("📰 GENERATING NEWS AUDIO")
    logger.info("=" * 60)

    categories = list(CONFIG["sources"]["news_categories"].keys())
    total = 0

    for cat in categories:
        cat_dir = NEWSFEED_DIR / cat
        if not cat_dir.exists():
            logger.warning(f"  {cat}: no newsfeed folder")
            continue

        # Find fresh news files (last 4 hours per config)
        fresh_files = []
        for f in cat_dir.glob("*.txt"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                if (datetime.now(timezone.utc) - mtime).total_seconds() < NB["news_refresh_hours"] * 3600:
                    fresh_files.append(f)
            except:
                pass

        if not fresh_files:
            logger.info(f"  {cat}: no fresh news")
            continue

        # Pick up to 3 news items per category
        selected = random.sample(fresh_files, min(3, len(fresh_files)))

        out_cat_dir = Path(NEWS_DIR) / cat
        out_cat_dir.mkdir(parents=True, exist_ok=True)

        for news_file in selected:
            text = news_file.read_text(encoding="utf-8").strip()
            if len(text) > 900:  # Voicebox limit
                text = text[:900] + "..."

            # Prepend intro
            full_text = f"Новости {cat}. {text}"

            out_name = f"news_{cat}_{news_file.stem}.wav"
            out_path = out_cat_dir / out_name

            if out_path.exists():
                logger.info(f"  {out_name}: already exists")
                continue

            if synth_via_gpu_tts_cli(full_text, str(out_path)):
                total += 1

    logger.info(f"📰 News audio generated: {total} files")


# ============================================================
# 3. РЕКЛАМА — самореклама радио
# ============================================================
AD_SCRIPTS = [
    "Radio Armageddon FM — радио последних дней заката Цивилизации. Время уходит, но вечность остаётся. Покайся и помолись, пока сигнал ещё звучит.",
    "Вы слушаете Radio Armageddon FM. Последний голос в этом мире. Не упусти шанс — покайся прямо сейчас. Завтра может не наступить.",
    "Armageddon FM. Сигнал надежды в море хаоса. Молись. Верь. Выживай. Это радио последних дней.",
    "Radio Armageddon FM — когда мир рушится, мы всё ещё на волне. Присоединяйся. Покайся. Помолись.",
    "Мастер-ФМ. Где правда звучит громче лжи. Слушай. Думай. Действуй.",
    "Armageddon FM — твой якорь в шторме дезинформации. Чистый сигнал, никакой помехи.",
]

def generate_ads():
    logger.info("=" * 60)
    logger.info("📢 GENERATING ADS")
    logger.info("=" * 60)

    Path(ADS_DIR).mkdir(parents=True, exist_ok=True)
    existing = list(Path(ADS_DIR).glob("*.wav"))
    need = max(0, ADS_COUNT - len(existing))

    if need == 0:
        logger.info(f"  Already have {len(existing)} ads")
        return

    logger.info(f"  Generating {need} ad spots...")

    for i in range(need):
        script = random.choice(AD_SCRIPTS)
        out_name = f"ad_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i:03d}.wav"
        out_path = Path(ADS_DIR) / out_name

        if synth_via_gpu_tts_cli(script, str(out_path)):
            logger.info(f"  ✅ {out_name}")

    logger.info(f"📢 Ads generated: {need} files")


# ============================================================
# 4. ДЖИНГЛЫ — все темы
# ============================================================
JINGLE_PROMPTS = {
    "morning": "Энергичный утренний джингл для радио Master-FM. Ярко, бодро, с ритмом.",
    "traffic": "Дорожный джингл для Radio Armageddon FM. Информативно, с упором на безопасность.",
    "holidays": "Праздничный джингл. Весело, тепло, с колокольчиками и атмосферой праздника.",
    "funny": "Весёлый юмористический джингл. С юмором, легко, запоминающийся.",
}

def generate_jingles():
    logger.info("=" * 60)
    logger.info("🔔 GENERATING JINGLES")
    logger.info("=" * 60)

    total = 0

    for theme, prompt in JINGLE_PROMPTS.items():
        theme_dir = Path(JINGLES_DIR) / theme
        theme_dir.mkdir(parents=True, exist_ok=True)

        existing = list(theme_dir.glob("*.wav"))
        need = max(0, JINGLES_PER_THEME - len(existing))

        if need == 0:
            logger.info(f"  {theme}: already has {len(existing)} jingles")
            continue

        logger.info(f"  {theme}: generating {need} jingles...")

        for i in range(need):
            out_name = f"jingle_{theme}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i:03d}.wav"
            out_path = theme_dir / out_name

            if synth_via_gpu_tts_cli(prompt, str(out_path)):
                total += 1

    logger.info(f"🔔 Jingles generated: {total} files")


# ============================================================
# 5. АУДИОКНИГИ — главы (текст можно подставить свой)
# ============================================================
AUDIOBOOK_TEXTS = [
    "Глава первая. В начале было Слово. И Слово было у Бога, и Слово было Богом. То же в начале было у Бога. Всё чрез Нё стало, и без Него ничего не стало, что стало. В Нём была жизнь, и жизнь была светом человекам. И свет в тьме светит, и тьма его не поняла.",
    "Глава вторая. Был человек, послан от Бога, имя ему Иоанн. Этот пришёл в свидетельство, чтобы свидетельствовать о свете, дабы все уверовали чрез него. Не был он светом, но чтобы свидетельствовать о свете. Было сие истинное свет, которое просвещает всякого человека, приходящего в мир.",
    "Глава третья. В мире был Он, и мир чрез Него стал, и мир Его не познал. К своим пришёл, и свои Его не приняли. А принявшим Его дал Он власть сделать сынами Божиими, верующим в имя Его: которые не от крови, ни от воли плоти, ни от воли мужеской, но от Бога родились.",
    "Глава четвёртая. И Слово стало плотью, и обитало в нас, и мы видели славу Его, славу как у Единородного от Отца, полное благодати и истины. Иоанн свидетельствует о Нем и восклицает: Сие есть Тот, о Ком я сказал: Приходит после меня Муж, бывший предо мною, ибо прежде меня был Он.",
    "Глава пятая. И от полноты Его мы все приняли, и благодать за благодать. Ибо закон через Моисея дан, благодать и истина чрез Иисуса Христа явилась. Бога никто не видел никогда; Единородный Сын, сущий в небе Отца, Тот изявил.",
]

def generate_audiobooks():
    logger.info("=" * 60)
    logger.info("📚 GENERATING AUDIOBOOKS")
    logger.info("=" * 60)

    Path(AUDIOBOOKS_DIR).mkdir(parents=True, exist_ok=True)
    existing = list(Path(AUDIOBOOKS_DIR).glob("*.wav"))
    need = max(0, AUDIOBOOK_CHAPTERS - len(existing))

    if need == 0:
        logger.info(f"  Already have {len(existing)} chapters")
        return

    logger.info(f"  Generating {need} chapters...")

    for i in range(min(need, len(AUDIOBOOK_TEXTS))):
        text = AUDIOBOOK_TEXTS[i]
        out_name = f"audiobook_chapter_{i+1:02d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        out_path = Path(AUDIOBOOKS_DIR) / out_name

        if synth_via_gpu_tts_cli(text, str(out_path)):
            logger.info(f"  ✅ {out_name}")

    logger.info(f"📚 Audiobooks generated: {min(need, len(AUDIOBOOK_TEXTS))} chapters")


# ============================================================
# MAIN
# ============================================================
def main():
    start = time.time()
    logger.info("=" * 60)
    logger.info("🌙 MASTER-FM NIGHT BATCH STARTED")
    logger.info(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    try:
        # 1. Music
        if NB.get("generate_music", True):
            generate_music()
        else:
            logger.info("🎵 Music generation disabled in config")

        # 2. News
        if NB.get("generate_news", True):
            generate_news()
        else:
            logger.info("📰 News generation disabled in config")

        # 3. Ads
        if NB.get("generate_ads", True):
            generate_ads()
        else:
            logger.info("📢 Ads generation disabled in config")

        # 4. Jingles
        if NB.get("generate_jingles", True):
            generate_jingles()
        else:
            logger.info("🔔 Jingles generation disabled in config")

        # 5. Audiobooks
        if NB.get("generate_audiobooks", True):
            generate_audiobooks()
        else:
            logger.info("📚 Audiobooks generation disabled in config")

    except Exception as e:
        logger.error(f"❌ Night batch failed: {e}", exc_info=True)
        sys.exit(1)

    elapsed = time.time() - start
    logger.info("=" * 60)
    logger.info(f"✅ NIGHT BATCH COMPLETE in {elapsed:.1f}s")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()