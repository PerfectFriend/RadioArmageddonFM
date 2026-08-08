# RadioArmageddonFM — Платформа AI-радиостриминга

**Стек:** ACE-Step 1.5 (генерация музыки) + Voicebox TTS (локальный, Kokoro/LuxTTS/Qwen3-TTS) + ffmpeg (сборка/даккинг)

---

## Обзор

RadioArmageddonFM — это **полностью локальный** пайплайн генерации контента для AI-радио. Он создаёт готовые к эфиру аудио-сегменты, комбинируя:

- **ACE-Step** — GPU-ускоренная генерация музыки (DiT-модель, 6GB VRAM tier2, `batch_size=1` для стабильности)
- **Voicebox** — Локальный TTS-сервер (jamiepine/voicebox v0.5.0, REST API + MCP), работает на CPU (Kokoro) или GPU (LuxTTS/Qwen3-TTS)
- **ffmpeg** — Профессиональная сборка аудио: даккинг, кроссфейды, конвертация форматов

Всё работает локально на Windows (Tailscale mesh для удалённого доступа). Никаких облачных API, никаких подписок.

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    RadioArmageddonFM                        │
├──────────────────┬──────────────────────┬───────────────────┤
│   ACE-Step API   │    Voicebox TTS      │      ffmpeg       │
│  (127.0.0.1:8001)│    (127.0.0.1:7860)  │   (system path)   │
├──────────────────┼──────────────────────┼───────────────────┤
│ • Музыкальные кровати │ • Озвучка / DJ-интро │ • Микс с дакингом │
│ • Джинглы           │ • Новости/погода     │ • Конкатенация    │
│ • Рекламные кровати │ • Клонирование голоса│ • MP3 192kbps     │
│ • Наследование стиля│                      │ • Конвертация     │
└──────────────────┴──────────────────────┴───────────────────┘
```

---

## Workflows

| Команда | Назначение | Длительность |
|---------|------------|--------------|
| `jingle` | ID станции + музыкальная кровать | 8с |
| `ad` | Рекламный спот | 20с |
| `forecast` | Погодный блок | 25с |
| `newsfeed` | Новостная лента | 30с |

**Ключевая фича:** параметр `--style` заставляет музыкальную кровать **наследовать жанр текущего радио-блока** (напр. `--style "dark psytrance 148bpm"`). Кровать автоматически приглушается, чтобы голос оставался на переднем плане.

---

## Быстрый старт

### Требования

- Windows 10/11, GPU NVIDIA (проверено: RTX 3060 Laptop 6GB)
- Python 3.11+, пакетный менеджер uv
- ffmpeg в PATH
- Tailscale (для mesh-доступа)

### ACE-Step (Музыка)

```bash
# Клонирование и настройка (однократно)
git clone https://github.com/ace-step/ACE-Step-1.5.git
cd ACE-Step-1.5
uv sync

# Фикс torchao для torch 2.5.1+cu121
uv pip install torchao==0.9.0

# Скачивание весов (4.8GB + 3.7GB + 1.2GB + 337MB)
python scripts/download-models.py

# Конфиг .env
echo "ACESTEP_INIT_LLM=false" > .env
echo "ACESTEP_NO_INIT=false" >> .env
```

### Voicebox (TTS)

```bash
# Скачать MSI с GitHub Releases (jamiepine/voicebox v0.5.0)
# Voicebox_0.5.0_x64_en-US.msi (~543MB)

# Установка через PowerShell (нужен UAC)
powershell -Command "Start-Process msiexec -ArgumentList '/i','Voicebox_0.5.0_x64_en-US.msi','/qn','/norestart' -Verb RunAs -Wait"

# Запуск сервера
"C:\Program Files\Voicebox\voicebox-server.exe" --host 127.0.0.1 --port 7860
```

### RadioArmageddonFM

```bash
git clone https://github.com/PerfectFriend/RadioArmageddonFM.git
cd RadioArmageddonFM

# Запуск сервисов (в отдельных терминалах)
# Терминал 1: ACE-Step API
cd C:\Users\yusya\ACE-Step-1.5 && PYTHONPATH= .venv\Scripts\python.exe -m acestep.api_server --host 0.0.0.0 --port 8001

# Терминал 2: Voicebox (уже запущен)

# Генерация контента
python radio_gen.py jingle   --voice-text "Вы слушаете Radio Armageddon FM!" --out out/jingle1.mp3
python radio_gen.py ad       --text "Купите наш крипто-курс сегодня!" --style "dark psytrance 148bpm" --out out/ad1.mp3
python radio_gen.py forecast --text "Москва: 22°C, ясно" --out out/forecast1.mp3
python radio_gen.py newsfeed --text "Bitcoin обновил исторический максимум" --out out/news1.mp3
```

---

## Конфигурация

Переменные окружения:

```bash
ACE_STEP_URL=http://127.0.0.1:8001      # или Tailscale IP:8001
VOICEBOX_URL=http://127.0.0.1:7860
ACE_STEP_DIR=C:\Users\yusya\ACE-Step-1.5
VOICEBOX_DATA_DIR=C:\Users\yusya\data
```

---

## Удалённый доступ через Tailscale

```bash
# На машине-сервере
tailscale ip -4  # напр. 100.124.152.97

# Файрвол (PowerShell Admin)
Start-Process netsh -ArgumentList 'advfirewall firewall add rule name=ACE-Step-API-8001 dir=in action=allow protocol=TCP localport=8001' -Verb RunAs -Wait

# С клиентской машины
export ACE_STEP_URL=http://100.124.152.97:8001
python radio_gen.py jingle --voice-text "Удалённая генерация!" --out out/remote.mp3
```

---

## Бенчмарки (RTX 3060 Laptop 6GB)

| Длительность | Фаза DiT | Полный цикл | Коэф. реального времени |
|--------------|----------|-------------|------------------------|
| 30с          | ~3с      | ~35с        | ~1.1x                  |
| 4мин         | 18-20с   | 45-58с      | ~4.3x                  |
| 8мин         | 42с      | 75с         | ~6.4x                  |

*DiT масштабируется линейно ~11-12x реального времени. Накладные расходы полного цикла (~23с) доминируют на коротких треках.*

---

## Лицензия

MIT — делай что хочешь, но держи хаос в живых.

---

## Связанное

- [ACE-Step](https://github.com/ace-step/ACE-Step-1.5) — Модель генерации музыки
- [Voicebox](https://github.com/jamiepine/voicebox) — Локальный TTS-студия
- [GodModeCoder](https://github.com/PerfectFriend/GodModeCoder) — Фреймворк эволюционного графа

---

*Сгенерировано Инквизицией. Вещание на всех частотах.*