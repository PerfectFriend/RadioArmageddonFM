# Radio Armageddon FM (Master-FM) — HOWTOUSE.md

> **Автономное AI-радио "Master-FM" — 24/7 стриминг, генерация музыки через MusicGen (AMD 780M DirectML), TTS через Qwen3-TTS, новостная лента, джинглы, реклама, аудиокниги. Полностью локальное, GPU-ускоренное (DirectML), запускается одной командой.**

---

## 🎯 QUICK START (TL;DR)

```bash
# 1. Клонировать
git clone https://github.com/<your-username>/RadioArmageddonFM.git
cd RadioArmageddonFM

# 2. Скачать модель MusicGen (один раз, ~300 MB)
# См. раздел "Модели" ниже

# 3. Виртуальное окружение
python -m venv venv
venv\Scripts\activate  # Linux/Mac: source venv/bin/activate

# 4. Зависимости
pip install -r requirements.compiled

# 4.1. DirectML / GPU проверка
python -c "import torch, torch_directml; print('CUDA:', torch.cuda.is_available(), 'DML:', torch_directml.is_available())"

# 5. Запуск DJ (Master-FM на порту 8090)
python scripts/dj.py
# Открыть в браузере: http://localhost:8090/radio
```

---

## 📁 СТРУКТУРА ПРОЕКТА

```
RadioArmageddonFM/
├── config.yaml                 # Главная конфигурация (все настройки)
├── requirements.compiled       # Зависимости (pip install -r)
├── silence_header.mp3          # MP3 заголовок для стрима (9 KB, важен!)
├── config.yaml                 # Основная конфигурация
├── dj.py                       # DJ стейшн (HTTP стрим на :8090/radio)
├── dj_pipeline.py              # Pipeline: генерация музыки + микширование новостей
├── musicgen_directml.py        # MusicGen через DirectML (AMD 780M)
├── audio_stitcher.py           # Сшивание треков в часовые блоки
├── config.yaml                 # Вся конфигурация радио
├── scripts/
│   ├── dj.py                   # Основной DJ сервер (порт 8090)
│   ├── day_breaking_news.py    # Сбор breaking news
│   ├── gpu_tts_cli.py          # TTS CLI
│   └── *.py                    # Остальные утилиты
├── musicgen_directml.py        # MusicGen через DirectML
├── audio_stitcher.py           # Сшивка треков в часовые блоки
├── config.yaml                 # Конфиг радио
├── requirements.compiled       # Зависимости
├── silence_header.mp3          # MP3 заголовок (9 KB, важен!)
├── config.yaml                 # Конфиг
├── dj.py                       # DJ сервер
├── dj_pipeline.py              # Pipeline
├── musicgen_directml.py        # MusicGen DirectML
├── audio_stitcher.py           # Сшиватель
├── config.yaml                 # Конфиг
├── requirements.compiled       # Зависимости
├── silence_header.mp3          # MP3 заголовок
├── models/
│   └── musicgen-small/         # MusicGen модель (~300 MB, скачивается отдельно)
├── cache/                      # Кэш контента (регенерируется)
│   ├── music/                  # Музыка по стилям
│   ├── news/                   # TTS новости
│   ├── jingles/                # Джинглы
│   ├── ads/                    # Реклама
│   ├── audiobooks/             # Аудиокниги
│   └── jingles/                # Джинглы
├── music_output/               # Сгенерированные треки MusicGen
├── radio_output/               # Готовые часовые блоки
├── cache/                      # Кэш (регенерируется)
├── radio_output/               # Готовые часовые миксы
├── music_output/               # Сырые треки MusicGen
├── logs/                       # Логи
├── config.yaml                 # Конфиг
├── requirements.compiled       # Зависимости
├── silence_header.mp3          # MP3 заголовок
├── config.yaml                 # Конфиг
├── dj.py                       # DJ сервер
├── dj_pipeline.py              # Pipeline
├── musicgen_directml.py        # MusicGen
├── audio_stitcher.py           # Сшиватель
├── config.yaml                 # Конфиг
├── requirements.compiled       # Зависимости
├── silence_header.mp3          # MP3 заголовок
├── scripts/
│   ├── dj.py                   # DJ сервер (порт 8090)
│   ├── day_breaking_news.py    # Breaking news
│   ├── gpu_tts_cli.py          # TTS CLI
│   └── *.py
├── requirements.compiled       # Зависимости
├── silence_header.mp3          # MP3 заголовок
├── config.yaml                 # Конфиг
├── dj.py                       # DJ сервер
├── dj_pipeline.py              # Pipeline
├── musicgen_directml.py        # MusicGen
├── audio_stitcher.py           # Сшиватель
├── config.yaml                 # Конфиг
├── requirements.compiled       # Зависимости
├── silence_header.mp3          # MP3 заголовок
└── README.md                   # Этот файл
```

---

## 🎛 КОНФИГУРАЦИЯ (config.yaml) — ВСЁ ЗДЕСЬ

```yaml
radio:
  name: "Master-FM"
  stream_port: 8090
  stream_mount: "/radio"
  bitrate: 128
  sample_rate: 44100

  schedule:
    music_block_min: 15
    jingle_every_tracks: 3
    news_every_min: 30
    ad_every_min: 15
    audiobook_at_hours: [0, 1, 2, 3, 4]

  modes:
    night_batch:
      enabled: true
      start_hour: 20
      end_hour: 7
      generate_music: true
      generate_news: true
      generate_ads: true
      generate_jingles: true
      generate_audiobooks: true
      music_per_style: 10
      music_duration_sec: 180

    day_mode:
      enabled: true
      generate_music: false
      generate_news: true
      generate_ads: false
      generate_jingles: false
      generate_audiobooks: false
      news_breaking_only: true
      news_check_min: 15

  generation:
    music_per_style: 10
    news_hold_min: 120
    ad_hold_min: 240
    jingle_hold_min: 1440

  sources:
    music_styles:
      rock: "energetic rock, electric guitars, drums, 120 BPM"
      jazz: "calm jazz, saxophone, double bass, 90 BPM"
      electronic: "electronic music, synthesizers, beat 128 BPM"
      ambient: "ambient, atmospheric pads, slow tempo"
      chiptune: "chiptune, 8-bit, retro game music"
      classical: "classical orchestral music, piano"

  dj:
    voice_profile: "e7013ccf-70c7-4f22-a277-e6b3e4ddc4ef"
    engine: "qwen_custom_voice"
    language: "ru"
    max_text_chars: 900

  paths:
    cache_root: "cache"
    music_dir: "cache/music"
    news_dir: "cache/news"
    ads_dir: "cache/ads"
    jingles_dir: "cache/jingles"
    audiobooks_dir: "cache/audiobooks"
    logs_dir: "logs"
```

---

## 🤖 МОДЕЛИ (СКАЧАТЬ ОДИН РАЗ)

### MusicGen (MusicGen-small, ~300 MB)
```bash
# Папка должна быть: models/musicgen-small/
# Скачать с HuggingFace:
# https://huggingface.co/facebook/musicgen-small/tree/main

# Структура:
models/
└── musicgen-small/
    ├── config.json
    ├── pytorch_model.bin
    └── ... (остальные файлы модели)
```

**Важно:** модель должна лежать в `models/musicgen-small/` относительно корня проекта.

---

## 🚀 ЗАПУСК СЕРВИСОВ

### 1. DJ Master-FM (основной стрим) — ПОРТ 8090
```bash
venv\Scripts\python.exe scripts\dj.py
# Открыть: http://localhost:8090/radio
```

### 2. Music Generation Pipeline (генерация музыки)
```bash
python dj_pipeline.py --continuous --interval 60
# или однократно:
python dj_pipeline.py --generate-music
```

### 3. Voice / TTS (голос, новости, джинглы)
```bash
# Проверка TTS
python scripts\gpu_tts_cli.py --text "Тест голоса" --output test.wav
```

### 4. MusicGen DirectML (прямая генерация)
```bash
python -c "
from musicgen_directml import MusicGenDirectML
mg = MusicGenDirectML()
paths = mg.generate_batch(count=3, preset_name='morning')
print('Generated:', paths)
"
```

---

## ⚙️ ТРЕБОВАНИЯ (System Requirements)

| Компонент | Минимум | Рекомендуется |
|-----------|---------|---------------|
| **OS** | Windows 10/11 (WSL2 Ubuntu 22.04+) | Windows 11 + WSL2 |
| **Python** | 3.11+ | 3.11 или 3.12 |
| **GPU** | AMD 780M / любая с DirectML | AMD 780M / RTX 3060+ |
| **VRAM** | 4 GB | 8+ GB |
| **RAM** | 8 GB | 16+ GB |
| **Disk** | 10 GB | 20+ GB |
| **FFmpeg** | В PATH | В PATH |
| **Python** | 3.11+ | 3.11/3.12 |

### GPU / DirectML проверка
```python
import torch, torch_directml
print("CUDA:", torch.cuda.is_available())
print("DirectML:", torch_directml.is_available())
if torch_directml.is_available():
    dml = torch_directml.device()
    print("Device:", dml)
```

---

## 📦 ЧТО НЕ В ГИТ (передать отдельно на флешке/облаком)

Следующие файлы/папки в `.gitignore` и **НЕ** в репозитории — передавай отдельно:

| Что | Источник | Куда положить на новом ноутбуке | Размер |
|-----|----------|--------------------------------|--------|
| **MusicGen модель** | `models/musicgen-small/` | `models/musicgen-small/` | ~300 MB |
| **Кэш контента** | `cache/` | `cache/` | ~100-500 MB |
| **YOLO веса** | `yolo11n.pt` | корень проекта | 5 MB |

**На флешке/облаке подготовь папку `Radiofiles/`:**

```
Radiofiles/
├── models/
│   └── musicgen-small/     # ~300 MB
├── cache/                   # ~100-500 MB (опционально)
└── yolo11n.pt              # 5 MB
```

**На новом ноутбуке:**
```bash
# После git clone
cd RadioArmageddonFM

# 1. Распаковать модели
cp -r /путь/к/флешке/Radiofiles/models ./

# 2. Опционально: кэш (чтобы не регенерить)
cp -r /путь/к/флешке/Radiofiles/cache ./

# 3. YOLO веса
cp /путь/к/флешке/Radiofiles/yolo11n.pt ./
```

Основные пакеты:
```
torch==2.4.1+cu118
torch-directml==0.2.5
torchaudio==2.4.1
audiocraft==1.3.0
torchaudio==2.4.1
torchvision==0.19.1
torchaudio==2.4.1
audiocraft==1.3.0
ffmpeg-python==0.2.8
pyyaml==6.0.3
rich==14.3.3
torch-directml==0.2.5
torch_directml==0.2.5
```

Установка:
```bash
pip install -r requirements.compiled
# или
pip install -r requirements.txt
```

---

## 🎵 ПРОВЕРКА РАБОТОСПОСОБНОСТИ

### 1. DJ стрим
```bash
python scripts\dj.py
# Открыть http://localhost:8090/radio в браузере/плеере
```

### 2. MusicGen тест
```python
from musicgen_directml import MusicGenDirectML
mg = MusicGenDirectML()
paths = mg.generate_batch(count=1, preset_name="morning")
print("Generated:", paths)
```

### 3. TTS тест
```bash
python scripts\gpu_tts_cli.py --text "Тест голоса Master FM" --output test_voice.wav
```

### 4. Проверка стрима
```bash
# В браузере: http://localhost:8090/radio
# В VLC: Открыть URL -> http://localhost:8090/radio
# curl -I http://localhost:8090/radio
```

---

## 🔧 ЧАСТЫЕ ПРОБЛЕМЫ И РЕШЕНИЯ

| Проблема | Решение |
|----------|---------|
| `ModuleNotFoundError: hermes_agent` | `pip install -e .` в папке hermes-agent |
| `ModuleNotFoundError: audiocraft` | `pip install audiocraft` |
| `torch_directml not available` | `pip install torch-directml` + обновить драйверы AMD |
| `CUDA out of memory` | Уменьшить `duration` в пресетах, использовать CPU |
| `silence_header.mp3 not found` | Запустить `generate_silence_header.py` |
| `Model not found` | Скачать `musicgen-small` в `models/musicgen-small/` |
| `DirectML not available` | `pip install torch-directml` + обновить драйверы AMD Adrenalin |
| `CUDA out of memory` | Уменьшить `duration` в пресетах config.yaml |
| `FFmpeg not found` | Установить FFmpeg и добавить в PATH |
| `Port 8090 in use` | Закрыть другой процесс или сменить порт в config.yaml |

---

## 📡 АРХИТЕКТУРА (Кратко)

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   DJ (dj.py)    │────▶│  FFmpeg Stream  │────▶│  HTTP :8090/radio│
│  Плейлист, кэш  │     │  Mastering цепочка│    │  MP3 Stream     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Cache/        │     │   FFmpeg        │     │  HTTP Clients   │
│  music/news/    │     │  Mastering:     │     │  Browser/VLC/   │
│  jingles/ads    │     │  HPF/Gate/EQ/   │     │  Phone/Telegram │
│  audiobooks     │     │  Loudnorm/Limiter│    │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │
        ▼
┌─────────────────┐     ┌─────────────────┐
│  MusicGen       │     │  TTS (Qwen3-    │
│  DirectML       │     │  TTS / Voicebox)│
│  (AMD 780M)     │     │  CPU/DirectML   │
└─────────────────┘     └─────────────────┘
```

---

## 📋 ЧЕКЛИСТ ПЕРЕД ЗАПУСКОМ

- [ ] Python 3.11+ + venv
- [ ] `pip install -r requirements.compiled`
- [ ] `models/musicgen-small/` на месте
- [ ] `silence_header.mp3` (9 KB) в корне
- [ ] `ffmpeg` в PATH (`ffmpeg -version`)
- [ ] DirectML работает (`python -c "import torch_directml; print(torch_directml.is_available())"`)
- [ ] Порт 8090 свободен
- [ ] `python scripts/dj.py` → "On air! Listen: http://localhost:8090/radio"
- [ ] Стрим играет в браузере/VLC: `http://localhost:8090/radio`

---

## 📞 ПОДДЕРЖКА

- **Issues:** GitHub Issues в этом репо
- **Логи:** `logs/` папка + консоль DJ
- **Конфиг:** Только `config.yaml` — всё остальное не трогать
- **Кэш:** `cache/` — можно удалять, перегенерируется

---

## 📜 ЛИЦЕНЗИЯ

Проект для внутреннего использования Мастера Инквизитора.
Код открыт для изучения, коммерческое использование — по согласованию.

---

**Версия:** 1.0 (Master-FM Autonomous AI Radio)
**Автор:** Master Inquisitor @ Radio Armageddon FM
**Последнее обновление:** 2026-08-08