#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Мастер-ФМ: ДНЕВНОЙ РЕЖИМ — генерация срочных новостей (breaking news).
Запускается по cron каждые 15 минут с 07:00 до 20:00.
Только CPU-TTS (через отдельный процесс gpu_tts_cli.py), остальное берётся из кэша.
"""
import os
import sys
import time
import random
import yaml
import subprocess
import tempfile
import shutil

RADIO_ROOT = r"C:\Users\tomas\ai-radio"
CONFIG_PATH = os.path.join(RADIO_ROOT, "config.yaml")

# Путь к GPU-TTS CLI (запускает CPU-TTS в отдельном процессе)
GPU_TTS_CLI = os.path.join(RADIO_ROOT, "scripts", "gpu_tts_cli.py")
REF_WAV = "C:/Users/tomas/Voicebox/data/profiles/ac9a52ff-0c1a-44c3-a378-959542178e06/156c65ec-7000-45cc-858b-daa368340c1a.wav"


def synth_via_gpu_tts_cli(text: str, out_path: str) -> bool:
    """Озвучить текст через gpu_tts_cli.py (отдельный процесс, память освобождается)."""
    # Пишем текст во временный файл
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", delete=False) as tf:
        tf.write(text)
        text_file = tf.name

    try:
        # Запускаем GPU-TTS CLI
        env = os.environ.copy()
        env["PYTHONPATH"] = ""
        env["VIRTUAL_ENV"] = ""
        env["GPU_TTS_REF_WAV"] = REF_WAV
        
        cmd = [sys.executable, GPU_TTS_CLI, text_file, out_path]
        
        print(f"[tts] synth: {text[:60]}...", flush=True)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)
        
        if result.returncode != 0:
            print(f"  ! ошибка синтеза (code {result.returncode}): {result.stderr[-500:]}", flush=True)
            return False
        
        ok = os.path.exists(out_path) and os.path.getsize(out_path) > 1000
        if not ok:
            print(f"  ! синтез не удался: файл пустой или не создан", flush=True)
        else:
            print(f"[tts] ok: wrote {os.path.getsize(out_path)} bytes to {out_path}", flush=True)
        return ok
    except subprocess.TimeoutExpired:
        print(f"  ! таймаут синтеза (300с)", flush=True)
        return False
    except Exception as e:
        print(f"  ! ошибка запуска: {e}", flush=True)
        return False
    finally:
        try:
            os.unlink(text_file)
        except Exception:
            pass


# Примеры срочных новостей (в реальности агент будет подставлять актуальные)
BREAKING_NEWS_TEMPLATES = {
    "world": [
        "Срочные мировые новости. {event}. Подробности будут позже.",
        "Брекинг: {event}. Ситуация развивается.",
    ],
    "tech": [
        "Срочные новости технологий. {event}.",
        "Технологический брекинг: {event}.",
    ],
    "sport": [
        "Спортивные срочные новости. {event}!",
        "Брекинг спорта: {event}.",
    ],
    "local": [
        "Местные срочные новости. {event}.",
        "В городе прямо сейчас: {event}.",
    ],
}

BREAKING_EVENTS = {
    "world": [
        "в столице объявлено чрезвычайное положение из-за наводнения",
        "мировые лидеры подписали договор о снижении ядерных арсеналов",
        "крупная международная корпорация обанкротилась",
        "авиакатастрофа в Европе, есть жертвы",
    ],
    "tech": [
        "крупнейшая утечка данных за историю затронула миллионы пользователей",
        "ИИ-система впервые прошла тест Тьюринга в слепом режиме",
        "крупный хостинг-провайдер отключился, вдали тысячи сайтов",
        "новый вирус-шифровальщик атакует корпоративные сети по всему миру",
    ],
    "sport": [
        "футбольная команда внезапно сменила тренера за день до финала",
        "звезда НХЛ объявила о завершении карьеры на пике формы",
        "допинг-скандал на Олимпиаде: лишены медали три чемпиона",
        "рекорд стадиона побит: болельщики заполнили все места за час",
    ],
    "local": [
        "на главной магистрали города случилось крупное ДТП, движение перекрыто",
        "в центре города прорвалась теплотрасса, эвакуируют жителей",
        "пожар на складе химикатов: дымка видна по всему городу",
        "мэр объявил о внеплановых выборах в горсовет",
    ],
}


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["radio"]


def is_day_mode():
    """True если сейчас дневной режим (07:00-20:00)."""
    hour = time.localtime().tm_hour
    return 7 <= hour < 20


def get_cached_news_count(category, max_age_min=None):
    """Возвращает количество неистёкших кэшированных новостей в категории."""
    news_dir = os.path.join(RADIO_ROOT, "cache", "news", category)
    if not os.path.exists(news_dir):
        return 0
    
    if max_age_min is None:
        # Читаем из конфига
        cfg = load_config()
        max_age_min = cfg["generation"].get("news_hold_min", 120)
    
    now = time.time()
    max_age_sec = max_age_min * 60
    count = 0
    for f in os.listdir(news_dir):
        if f.endswith(".wav"):
            fpath = os.path.join(news_dir, f)
            mtime = os.path.getmtime(fpath)
            if now - mtime <= max_age_sec:
                count += 1
            else:
                # Удаляем устаревший файл
                try:
                    os.unlink(fpath)
                    print(f"  [cleanup] удалён устаревший: {f}")
                except Exception:
                    pass
    return count


def generate_breaking_news():
    """Генерирует 1-2 срочные новости случайной категории."""
    cfg = load_config()
    categories = list(cfg["sources"]["news_categories"].keys())
    
    # Выбираем 1-2 случайные категории для breaking news
    selected_cats = random.sample(categories, min(2, len(categories)))
    
    generated = 0
    for cat in selected_cats:
        # Проверяем, не слишком ли много новостей в кэше (лимит: news_hold_min = 120 мин)
        # Если файлов > 5, пропускаем — кэш достаточно полон
        if get_cached_news_count(cat) >= 5:
            print(f"[breaking] {cat}: кэш полон ({get_cached_news_count(cat)} файлов), пропуск")
            continue
           
        template = random.choice(BREAKING_NEWS_TEMPLATES[cat])
        event = random.choice(BREAKING_EVENTS[cat])
        text = template.format(event=event)
        
        # Имя файла с timestamp
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(RADIO_ROOT, "cache", "news", cat)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"breaking_{cat}_{ts}.wav")
        
        print(f"[breaking/{cat}] {text[:80]}...")
        if synth_via_gpu_tts_cli(text, out_path):
            print(f"  ✓ сохранено: {out_path}")
            generated += 1
        else:
            print(f"  ✗ ошибка генерации")
        
        time.sleep(1)  # небольшая пауза между генерациями
    
    return generated


def main():
    if not is_day_mode():
        print(f"[breaking] Сейчас не дневной режим ({time.strftime('%H:%M')}), выход")
        return
    
    print(f"[breaking] ===== ПРОВЕРКА СРОЧНЫХ НОВОСТЕЙ ({time.strftime('%H:%M:%S')}) =====")
    
    generated = generate_breaking_news()
    
    print(f"[breaking] Сгенерировано срочных новостей: {generated}")
    print(f"[breaking] ===== ЗАВЕРШЁНО =====")


if __name__ == "__main__":
    main()