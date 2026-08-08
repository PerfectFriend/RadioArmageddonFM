# RadioArmageddonFM — Plataforma de Streaming de Radio con IA

**Stack:** ACE-Step 1.5 (generación de música) + Voicebox TTS (local, Kokoro/LuxTTS/Qwen3-TTS) + ffmpeg (ensamblaje/ducking)

---

## Visión General

RadioArmageddonFM es una plataforma **totalmente local** de generación de contenido para radio con IA. Produce segmentos de audio listos para emitir combinando:

- **ACE-Step** — Generación de música acelerada por GPU (modelo DiT, 6GB VRAM tier2, batch_size=1 para estabilidad)
- **Voicebox** — Servidor TTS local (jamiepine/voicebox v0.5.0, REST API + MCP), funciona en CPU (Kokoro) o GPU (LuxTTS/Qwen3-TTS)
- **ffmpeg** — Ensamblaje profesional de audio con ducking, crossfades y conversión de formatos

Todos los componentes se ejecutan localmente en Windows (mesh Tailscale para acceso remoto). Sin APIs en la nube, sin cuotas de suscripción.

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                    RadioArmageddonFM                        │
├──────────────────┬──────────────────────┬───────────────────┤
│   ACE-Step API   │    Voicebox TTS      │      ffmpeg       │
│  (127.0.0.1:8001)│    (127.0.0.1:7860)  │   (system path)   │
├──────────────────┼──────────────────────┼───────────────────┤
│ • Camas musicales│ • Locución / Intros  │ • Mezcla ducking  │
│ • Jingles        │   de DJ              │ • Concatenación   │
│ • Camas publicidad│ • Noticias/clima    │ • MP3 192kbps     │
│ • Herencia estilo│ • Clonación voz      │ • Conversión fmt  │
└──────────────────┴──────────────────────┴───────────────────┘
```

---

## Workflows

| Comando | Propósito | Salida |
|---------|-----------|--------|
| `jingle` | ID de estación + cama musical | Jingle 8s |
| `ad` | Spot publicitario | Anuncio 20s |
| `forecast` | Parte meteorológica | Pronóstico 25s |
| `newsfeed` | Titulares de noticias | Noticias 30s |

**Característica clave:** El parámetro `--style` hace que la cama musical **herede el género del bloque actual de radio** (ej: `--style "dark psytrance 148bpm"`). La cama se atenúa automáticamente para que la voz quede por encima.

---

## Inicio Rápido

### Prerrequisitos

- Windows 10/11, GPU NVIDIA (probado: RTX 3060 Laptop 6GB)
- Python 3.11+, gestor de paquetes uv
- ffmpeg en PATH
- Tailscale (para acceso mesh)

### ACE-Step (Música)

```bash
# Clonar y configurar (una vez)
git clone https://github.com/ace-step/ACE-Step-1.5.git
cd ACE-Step-1.5
uv sync

# Arreglar torchao para torch 2.5.1+cu121
uv pip install torchao==0.9.0

# Descargar modelos (4.8GB + 3.7GB + 1.2GB + 337MB)
python scripts/download-models.py

# Configurar .env
echo "ACESTEP_INIT_LLM=false" > .env
echo "ACESTEP_NO_INIT=false" >> .env
```

### Voicebox (TTS)

```bash
# Descargar MSI desde GitHub releases (jamiepine/voicebox v0.5.0)
# Voicebox_0.5.0_x64_en-US.msi (~543MB)

# Instalar via PowerShell (UAC requerido)
powershell -Command "Start-Process msiexec -ArgumentList '/i','Voicebox_0.5.0_x64_en-US.msi','/qn','/norestart' -Verb RunAs -Wait"

# Lanzar servidor
"C:\Program Files\Voicebox\voicebox-server.exe" --host 127.0.0.1 --port 7860
```

### RadioArmageddonFM

```bash
git clone https://github.com/PerfectFriend/RadioArmageddonFM.git
cd RadioArmageddonFM

# Iniciar servicios (en terminales separadas)
# Terminal 1: ACE-Step API
cd C:\Users\yusya\ACE-Step-1.5 && PYTHONPATH= .venv\Scripts\python.exe -m acestep.api_server --host 0.0.0.0 --port 8001

# Terminal 2: Voicebox (ya corriendo)

# Generar contenido
python radio_gen.py jingle   --voice-text "¡Estás escuchando Radio Armageddon FM!" --out out/jingle1.mp3
python radio_gen.py ad       --text "¡Compra nuestro curso de crypto hoy!" --style "dark psytrance 148bpm" --out out/ad1.mp3
python radio_gen.py forecast --text "Moscú: 22°C, cielos despejados" --out out/forecast1.mp3
python radio_gen.py newsfeed --text "Bitcoin alcanza nuevo máximo histórico" --out out/news1.mp3
```

---

## Configuración

Variables de entorno:

```bash
ACE_STEP_URL=http://127.0.0.1:8001      # o Tailscale IP:8001
VOICEBOX_URL=http://127.0.0.1:7860
ACE_STEP_DIR=C:\Users\yusya\ACE-Step-1.5
VOICEBOX_DATA_DIR=C:\Users\yusya\data
```

---

## Acceso Remoto via Tailscale

```bash
# En máquina servidor
tailscale ip -4  # ej. 100.124.152.97

# Firewall (PowerShell Admin)
Start-Process netsh -ArgumentList 'advfirewall firewall add rule name=ACE-Step-API-8001 dir=in action=allow protocol=TCP localport=8001' -Verb RunAs -Wait

# Desde máquina cliente
export ACE_STEP_URL=http://100.124.152.97:8001
python radio_gen.py jingle --voice-text "¡Generación remota!" --out out/remote.mp3
```

---

## Benchmarks (RTX 3060 Laptop 6GB)

| Duración | Fase DiT | Ciclo Completo | Factor Tiempo Real |
|----------|----------|----------------|-------------------|
| 30s      | ~3s      | ~35s           | ~1.1x             |
| 4min     | 18-20s   | 45-58s         | ~4.3x             |
| 8min     | 42s      | 75s            | ~6.4x             |

*DiT escala linealmente ~11-12x tiempo real. Overhead de ciclo completo (~23s) domina tracks cortos.*

---

## Licencia

MIT — haz lo que quieras, pero mantén el caos vivo.

---

## Relacionados

- [ACE-Step](https://github.com/ace-step/ACE-Step-1.5) — Modelo de generación musical
- [Voicebox](https://github.com/jamiepine/voicebox) — Estudio TTS local
- [GodModeCoder](https://github.com/PerfectFriend/GodModeCoder) — Framework de grafo evolutivo

---

*Generado por la Inquisición. Transmitiendo en todas las frecuencias.*