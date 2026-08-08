# RadioArmageddonFM — AI Radio Streaming Platform

**Stack:** ACE-Step 1.5 (music generation) + Voicebox TTS (local, Kokoro/LuxTTS/Qwen3-TTS) + ffmpeg (assembly/ducking)

---

## Overview

RadioArmageddonFM is a fully-local AI radio content generation pipeline. It produces ready-to-air audio segments by combining:

- **ACE-Step** — GPU-accelerated music generation (DiT model, 6GB VRAM tier2, batch_size=1 for stability)
- **Voicebox** — Local TTS server (jamiepine/voicebox v0.5.0, REST API + MCP), runs on CPU (Kokoro) or GPU (LuxTTS/Qwen3-TTS)
- **ffmpeg** — Professional audio assembly with ducking, crossfades, and format conversion

All components run locally on Windows (Tailscale mesh for remote access). No cloud APIs, no subscription fees.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    RadioArmageddonFM                        │
├──────────────────┬──────────────────────┬───────────────────┤
│   ACE-Step API   │    Voicebox TTS      │      ffmpeg       │
│  (127.0.0.1:8001)│    (127.0.0.1:7860)  │   (system path)   │
├──────────────────┼──────────────────────┼───────────────────┤
│ • Music beds     │ • Voice-over / DJ    │ • Ducking mix     │
│ • Jingles        │   intros             │ • Concatenation   │
│ • Ads beds       │ • News/forecast      │ • MP3 192kbps     │
│ • Style inherit  │ • Voice cloning      │ • Format convert  │
└──────────────────┴──────────────────────┴───────────────────┘
```

---

## Workflows

| Command | Purpose | Output |
|---------|---------|--------|
| `jingle` | Station ID + music bed | 8s jingle |
| `ad` | Commercial spot | 20s ad |
| `forecast` | Weather report | 25s forecast |
| `newsfeed` | News headlines | 30s news |

**Key feature:** `--style` parameter makes the music bed **inherit the current radio block's genre** (e.g., `--style "dark psytrance 148bpm"`). The bed is automatically subdued so the voice stays on top.

---

## Quick Start

### Prerequisites

- Windows 10/11, NVIDIA GPU (tested: RTX 3060 Laptop 6GB)
- Python 3.11+, uv package manager
- ffmpeg in PATH
- Tailscale (for mesh access)

### ACE-Step (Music)

```bash
# Clone & setup (once)
git clone https://github.com/ace-step/ACE-Step-1.5.git
cd ACE-Step-1.5
uv sync

# Fix torchao for torch 2.5.1+cu121
uv pip install torchao==0.9.0

# Download models (4.8GB + 3.7GB + 1.2GB + 337MB)
python scripts/download-models.py

# Configure .env
echo "ACESTEP_INIT_LLM=false" > .env
echo "ACESTEP_NO_INIT=false" >> .env
```

### Voicebox (TTS)

```bash
# Download MSI from GitHub releases (jamiepine/voicebox v0.5.0)
# Voicebox_0.5.0_x64_en-US.msi (~543MB)

# Install via PowerShell (UAC required)
powershell -Command "Start-Process msiexec -ArgumentList '/i','Voicebox_0.5.0_x64_en-US.msi','/qn','/norestart' -Verb RunAs -Wait"

# Launch server
"C:\Program Files\Voicebox\voicebox-server.exe" --host 127.0.0.1 --port 7860
```

### RadioArmageddonFM

```bash
git clone https://github.com/PerfectFriend/RadioArmageddonFM.git
cd RadioArmageddonFM

# Start services (in separate terminals)
# Terminal 1: ACE-Step API
cd C:\Users\yusya\ACE-Step-1.5 && PYTHONPATH= .venv\Scripts\python.exe -m acestep.api_server --host 0.0.0.0 --port 8001

# Terminal 2: Voicebox (already running from above)

# Generate content
python radio_gen.py jingle   --voice-text "Вы слушаете Radio Armageddon FM!" --out out/jingle1.mp3
python radio_gen.py ad       --text "Buy our crypto course today!" --style "dark psytrance 148bpm" --out out/ad1.mp3
python radio_gen.py forecast --text "Moscow: 22°C, clear skies" --out out/forecast1.mp3
python radio_gen.py newsfeed --text "Bitcoin hits new ATH" --out out/news1.mp3
```

---

## Configuration

Environment variables:

```bash
ACE_STEP_URL=http://127.0.0.1:8001      # or Tailscale IP:8001
VOICEBOX_URL=http://127.0.0.1:7860
ACE_STEP_DIR=C:\Users\yusya\ACE-Step-1.5
VOICEBOX_DATA_DIR=C:\Users\yusya\data
```

---

## Tailscale Remote Access

```bash
# On server machine
tailscale ip -4  # e.g. 100.124.152.97

# Firewall (PowerShell Admin)
Start-Process netsh -ArgumentList 'advfirewall firewall add rule name=ACE-Step-API-8001 dir=in action=allow protocol=TCP localport=8001' -Verb RunAs -Wait

# From client machine
export ACE_STEP_URL=http://100.124.152.97:8001
python radio_gen.py jingle --voice-text "Remote generation!" --out out/remote.mp3
```

---

## Benchmarks (RTX 3060 Laptop 6GB)

| Duration | DiT Phase | Full Cycle | Real-time Factor |
|----------|-----------|------------|------------------|
| 30s      | ~3s       | ~35s       | ~1.1x            |
| 4min     | 18-20s    | 45-58s     | ~4.3x            |
| 8min     | 42s       | 75s        | ~6.4x            |

*DiT scales linearly ~11-12x real-time. Full-cycle overhead (~23s) dominates short tracks.*

---

## License

MIT — do whatever you want, but keep the chaos alive.

---

## Related

- [ACE-Step](https://github.com/ace-step/ACE-Step-1.5) — Music generation model
- [Voicebox](https://github.com/jamiepine/voicebox) — Local TTS studio
- [GodModeCoder](https://github.com/PerfectFriend/GodModeCoder) — Evolution graph framework

---

*Generated by the Inquisition. Broadcasting on all frequencies.*