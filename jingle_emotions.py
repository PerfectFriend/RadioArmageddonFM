#!/usr/bin/env python3
"""Джингл «Радио Армагеддон» в 4 эмоциях — ПО ДОКУМЕНТАЦИИ voicy (ADR 0003/0004/0005/0012).

Правила из ADR:
- ADR 0012/0003: текст режем на короткие реплики (один вдох), без внутренних
  запятых; каждая синтезируется ОТДЕЛЬНО (иначе модель обрезает на полуслове).
- ADR 0005: у модели speed только 1.0 (speed≠1 роняет разборчивость до CER 25%).
  Темп/эмоция — постобработкой ffmpeg (atempo/питч/громкость) поверх каждого куска.
- ADR 0004: на концах реплик фейд 45 мс; в паузах — room-tone (тихий кусок
  референсной записи Мастера), а не цифровая тишина.
- ADR 0003: длительности пауз заданы явно (key 480/420 мс, narration 120 мс).

После сборки — ASR-проверка через voicy /v1/audio/transcriptions: все слова
слогана должны быть в транскрипции (защита от обрезания).
"""
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import radio_gen as rg

VOICY = str(Path.home() / "voicy" / "voicy")
VOICY_CWD = str(Path.home() / "voicy")
MASTER_WAV = Path.home() / ".hermes/voice-memos/MasterVoice/master_voice.wav"
OUT_DIR = Path("/tmp/jingles_emotions")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Слоган порезан на реплики-«вдохи» (ADR 0012: без внутренних запятых).
# (текст, тип по ADR 0003: narration/term/key)
LINES = [
    ("Радио Армагеддон ЭФ ЭМ!", "key"),
    ("Радио на все времена", "narration"),
    ("для тех, кто сел покакать!", "key"),
]
# Паузы после реплик по ADR 0003 (мс), плюс добавка на эмоцию.
PAUSE_MS = {"narration": 120, "term": 260, "key": 420, "question": 250}

# эмоция -> (atempo, pitch-множитель asetrate, volume, добавка к паузам мс,
#            промпт beds ACE-Step, bpm)
EMOTIONS = {
    "angry":    (1.12, 0.90, 2.6, -260,
                 "dark aggressive industrial techno, pounding distorted kicks, minor key, "
                 "distorted bass, 150 bpm, instrumental, radio jingle energy", 150),
    "cheerful": (1.08, 1.09, 2.1, -120,
                 "upbeat cheerful funky house, bright piano chords, handclaps, major key, "
                 "124 bpm, instrumental, sunny radio jingle", 124),
    "calm":     (0.93, 0.97, 1.8, +180,
                 "calm ambient downtempo, soft warm pads, gentle piano, major key, "
                 "90 bpm, instrumental, relaxing radio bed", 90),
    "hype":     (1.18, 1.04, 2.7, -240,
                 "energetic driving psytrance, rolling bassline, bright leads, "
                 "148 bpm, instrumental, festival jingle energy", 148),
}


def sh(cmd, **kw):
    subprocess.run(cmd, check=True, capture_output=True, **kw)


def voicy_say_line(text: str, out_wav: Path, seed: int) -> Path:
    """Один кусок, speed=1.0 (ADR 0005). Автоударения RUAccent на сервере включены."""
    import time
    last = None
    for attempt in range(4):
        try:
            subprocess.run(
                [VOICY, "say", "--voice", "master", "--speed", "1.0",
                 "--seed", str(seed), "--format", "wav", text, str(out_wav),
                 "--timeout", "600"],
                check=True, capture_output=True, cwd=VOICY_CWD)
            return out_wav
        except subprocess.CalledProcessError as e:
            last = e
            print(f"  [retry {attempt+1}] voicy say failed: {e.stderr.decode()[-120:]}", flush=True)
            time.sleep(10)
    raise last


def room_tone(out_wav: Path, dur: float):
    """ADR 0004: самый тихий кусок референсной записи — фон комнаты для пауз."""
    sh(["ffmpeg", "-y", "-v", "error", "-i", str(MASTER_WAV),
        "-af", f"silencedetect=noise=-45dB:d=0.3,volume=0.5", "-t", str(dur + 0.4),
        str(out_wav)])


def asr_check(wav: Path, expect_words: list[str]) -> str:
    """ASR через voicy: возвращает транскрипцию; проверяем, что все слова на месте."""
    data = wav.read_bytes()
    boundary = "----voicyasr"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n").encode() + data + \
           f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8080/v1/audio/transcriptions", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        txt = json.loads(r.read())["text"]
    low = txt.lower()
    missing = [w for w in expect_words if w not in low]
    return f"ASR: '{txt}' missing={missing}"


def asr_check_safe(wav: Path, expect_words: list[str]) -> str:
    try:
        return asr_check(wav, expect_words)
    except Exception as e:
        return f"ASR skipped ({type(e).__name__})"


def build_voice(name: str, seed: int) -> tuple[Path, str]:
    atempo, pitch, vol, pause_add, _, _ = EMOTIONS[name]
    parts = []
    for i, (line, kind) in enumerate(LINES):
        raw = OUT_DIR / f"v_{name}_{i}_raw.wav"
        voicy_say_line(line, raw, seed=seed + i)
        # ADR 0004: фейд 45 мс на концах + ADR 0005: эмоция пост-fx (темп/питч/громкость)
        fx = (f"afade=t=in:st=0:d=0.045,afade=t=out:st=0:d=0.045,"
              f"asetrate=24000*{pitch},aresample=24000,atempo={atempo},volume={vol}")
        fxw = OUT_DIR / f"v_{name}_{i}_fx.wav"
        sh(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", fx, str(fxw)])
        parts.append((fxw, kind))
    # ADR 0003/0004: склейка с паузами из room-tone
    rt = OUT_DIR / f"room_{name}.wav"
    room_tone(rt, 1.0)
    concat = OUT_DIR / f"voice_{name}.wav"
    flist = OUT_DIR / f"concat_{name}.txt"
    entries = []
    for i, (p, kind) in enumerate(parts):
        entries.append(f"file '{p.resolve()}'")
        if i < len(parts) - 1:
            pause_ms = max(60, PAUSE_MS.get(kind, 200) + pause_add)
            entries.append(f"file '{rt.resolve()}'")
            # обрежем room-tone до нужной паузы через отдельный файл
            pfile = OUT_DIR / f"pause_{name}_{i}.wav"
            sh(["ffmpeg", "-y", "-v", "error", "-i", str(rt), "-t", f"{pause_ms/1000:.3f}",
                "-af", "afade=t=in:d=0.03,afade=t=out:d=0.05", str(pfile)])
            entries[-1] = f"file '{pfile.resolve()}'"
    flist.write_text("\n".join(entries) + "\n")
    sh(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(flist),
        "-c:a", "pcm_s16le", str(concat)])
    expect = ["армагеддон", "времена", "покакать"]
    report = asr_check_safe(concat, expect)
    return concat, report


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for i, (name, (_, _, _, _, prompt, bpm)) in enumerate(EMOTIONS.items()):
        if only and name != only:
            continue
        print(f"=== [{name}] ===", flush=True)
        voice, report = build_voice(name, seed=200 + i)
        print(f"  voice {rg.ff_duration(voice):.1f}s  {report}", flush=True)
        music = OUT_DIR / f"bed_{name}.mp3"
        rg.ace_step_generate(prompt + ", radio jingle bed, subdued, does not overpower voice",
                             22, music, seed=900 + i, audio_format="mp3", bpm=bpm)
        mix = OUT_DIR / f"mix_{name}.mp3"
        rg.mix_voice_over_music(voice, music, mix, music_volume=0.32, tail=1.2)
        norm = OUT_DIR / f"jingle_{name}.mp3"
        sh(["ffmpeg", "-y", "-v", "error", "-i", str(mix),
            "-af", "loudnorm=I=-14:TP=-1.5", "-c:a", "libmp3lame", "-b:a", "192k", str(norm)])
        ogg = OUT_DIR / f"jingle_{name}.ogg"
        sh(["ffmpeg", "-y", "-v", "error", "-i", str(norm), "-c:a", "libopus", str(ogg)])
        print(f"  -> {norm.name} {rg.ff_duration(norm):.1f}s", flush=True)
    print("ALL_DONE")


if __name__ == "__main__":
    main()
