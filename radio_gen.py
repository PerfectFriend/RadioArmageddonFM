#!/usr/bin/env python
"""
AI-Radio content generation workflows for the future AI radio streaming platform.

Stack:
  - ACE-Step 1.5 API (music beds / jingles)  -> http://127.0.0.1:8001 (or Tailscale IP)
  - Voicebox (jamiepine/voicebox, local TTS) -> REST API + MCP (voicebox.speak)
  - ffmpeg (final assembly / ducking)

Workflows: jingle, ad, forecast, newsfeed.

Usage:
  python radio_gen.py jingle   --voice-text "Вы слушаете КриптоИнквизицию!"  --out out/jingle1.mp3
  python radio_gen.py ad       --text "ad copy"                              --out out/ad1.mp3
  python radio_gen.py forecast --text "weather text"                         --out out/forecast1.mp3
  python radio_gen.py newsfeed --text "news text"                            --out out/news1.mp3
  # --style inherits the current radio block's genre into the music bed, e.g.:
  python radio_gen.py forecast --text "..." --style "dark psytrance, 148 bpm" --bed-volume 0.18
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ACE_STEP_URL = os.environ.get("ACE_STEP_URL", "http://127.0.0.1:8001")
VOICEBOX_URL = os.environ.get("VOICEBOX_URL", "http://127.0.0.1:7860")  # voicebox-server REST API
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

# ACE-Step server lifecycle (offload-to-CPU segfaults after repeated generations:
# the 6GB VRAM machine needs a FRESH server before every music task)
ACE_STEP_DIR = Path(os.environ.get("ACE_STEP_DIR", r"C:\Users\yusya\ACE-Step-1.5"))
ACE_STEP_VENV_PY = ACE_STEP_DIR / ".venv" / "Scripts" / "python.exe"
ACE_STEP_LAUNCH = [str(ACE_STEP_VENV_PY), "-m", "acestep.api_server",
                   "--host", "0.0.0.0", "--port", "8001"]

JINGLE_SECONDS = 8
AD_SECONDS = 20
FORECAST_SECONDS = 25
NEWS_SECONDS = 30


def _http_json(method: str, url: str, body=None, timeout: int = 60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        try:
            return json.loads(raw)
        except Exception:
            return raw.decode()


def ace_step_health(timeout: float = 5) -> bool:
    try:
        h = _http_json("GET", f"{ACE_STEP_URL}/health", timeout=timeout)
        return isinstance(h, dict) and h.get("data", {}).get("status") == "ok"
    except Exception:
        return False


def ace_step_restart(max_wait: float = 120) -> None:
    """Kill any running ACE-Step API server and launch a fresh one.

    The offload-to-CPU code path segfaults (exit 139) once the server has
    processed a few generations — memory fragmentation on 6GB VRAM. Fresh
    server per music task is the proven mitigation.
    """
    import subprocess
    # kill existing server processes
    try:
        out = subprocess.run(
            ["wmic", "process", "where",
             "name='python.exe' and commandline like '%acestep.api_server%'",
             "get", "processid"],
            capture_output=True, text=True, timeout=30)
        for line in out.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                subprocess.run(["taskkill", "/F", "/PID", line],
                               capture_output=True, timeout=15)
    except Exception:
        pass
    time.sleep(2)

    # launch fresh server
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)  # global hermes venv pollution breaks tokenizers
    proc = subprocess.Popen(
        ACE_STEP_LAUNCH, cwd=str(ACE_STEP_DIR), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    t0 = time.time()
    while time.time() - t0 < max_wait:
        if ace_step_health():
            return proc
        time.sleep(5)
    raise RuntimeError("ACE-Step server failed to start within %ss" % max_wait)

# ---------------------------------------------------------------------------
# ACE-Step music generation
# ---------------------------------------------------------------------------
def ace_step_generate(prompt: str, duration: int, out_path: Path, seed: int | None = None,
                      audio_format: str = "mp3", bpm: int | None = None) -> Path:
    """Submit a music generation task to ACE-Step and poll until done.

    Uses a FRESH server per task (offload segfault mitigation) and retries
    once if the server dies mid-generation.
    """
    body = {
        "prompt": prompt,
        "audio_duration": duration,
        "inference_steps": 8,
        "audio_format": audio_format,
        "batch_size": 1,
        "thinking": False,
    }
    if seed is not None:
        body["seed"] = seed
    if bpm is not None:
        body["bpm"] = bpm

    for attempt in range(2):
        if not ace_step_health():
            ace_step_restart()
        try:
            return _ace_step_generate_once(body, out_path)
        except (ConnectionResetError, ConnectionRefusedError, urllib.error.URLError) as e:
            print(f"  [ace-step] attempt {attempt+1} failed ({e}); restarting server...")
            ace_step_restart()
    raise RuntimeError("ACE-Step generation failed after retries")


def _ace_step_generate_once(body: dict, out_path: Path) -> Path:
    req = urllib.request.Request(
        f"{ACE_STEP_URL}/release_task",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        rj = json.loads(resp.read())
    # response is {"data": {"task_id": "...", "status": "queued", ...}, "code": 200, ...}
    inner = rj.get("data", rj) if isinstance(rj, dict) else {}
    task_id = inner.get("task_id") or rj.get("task_id")
    if not task_id:
        raise RuntimeError(f"release_task returned no task_id: {rj}")
    task_id = task_id.get("task_id") if isinstance(task_id, dict) else task_id

    t0 = time.time()
    audio_path = None
    while time.time() - t0 < 600:
        q = urllib.request.Request(
            f"{ACE_STEP_URL}/query_result",
            data=json.dumps({"task_id_list": json.dumps([task_id])}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(q, timeout=30) as resp:
            data = json.loads(resp.read())
        try:
            item = data[0] if isinstance(data, list) else data.get("data", [{}])[0]
        except Exception:
            item = data
        # item.result is a JSON string: '[{"file": "/v1/audio?path=...", "status": 1, ...}]'
        result = item.get("result") if isinstance(item, dict) else None
        if isinstance(result, str) and result.strip().startswith("["):
            try:
                tracks = json.loads(result)
                item = tracks[0] if tracks else item
            except Exception:
                pass
        status = item.get("status", 0)
        if status == 1:
            audio_path = (item.get("file") or item.get("audio_file_path")
                          or item.get("path") or item.get("audio_path"))
            # 'file' is a full API path like "/v1/audio?path=<url-encoded>"; extract path param
            if isinstance(audio_path, str) and audio_path.startswith("/v1/audio"):
                qs = audio_path.split("?", 1)[1]
                audio_path = urllib.parse.parse_qs(qs).get("path", [audio_path])[0]
            break
        if status == 2:  # failed
            raise RuntimeError(f"ACE-Step task failed: {item}")
        time.sleep(2)

    if not audio_path:
        raise RuntimeError("ACE-Step task timed out")

    # audio endpoint expects url-encoded absolute path
    encoded = urllib.parse.quote(str(audio_path))
    dl = urllib.request.urlopen(f"{ACE_STEP_URL}/v1/audio?path={encoded}", timeout=120)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        shutil.copyfileobj(dl, f)
    return out_path


# ---------------------------------------------------------------------------
# Voicebox TTS (voice-over / DJ voice) — local, REST API at :7860
# ---------------------------------------------------------------------------
def _vb_call(method: str, path: str, body=None, timeout: int = 300):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{VOICEBOX_URL}{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        try:
            return json.loads(raw)
        except Exception:
            return raw.decode()


def voicebox_create_preset_profile(name: str, engine: str, voice_id: str,
                                   language: str = "ru") -> str:
    """Create (or reuse) a preset-voice profile. Returns profile_id."""
    profiles = _vb_call("GET", "/profiles")
    items = profiles if isinstance(profiles, list) else (
        profiles.get("items") or profiles.get("profiles") or [])
    for p in items:
        if (p.get("name") == name and p.get("preset_engine") == engine
                and p.get("preset_voice_id") == voice_id):
            return p["id"]
    prof = _vb_call("POST", "/profiles", {
        "name": name, "language": language, "voice_type": "preset",
        "preset_engine": engine, "preset_voice_id": voice_id,
    })
    return prof["id"]


def voicebox_speak(text: str, out_path: Path, profile: str | None = None,
                   engine: str = "kokoro", language: str = "ru",
                   voice_id: str = "af_bella") -> Path:
    """Generate speech via Voicebox and copy the WAV to out_path.

    - Kokoro: tiny 82M model, fast CPU inference, 8 languages (ru included),
      preset voices (af_bella = female RU-capable). Zero VRAM — perfect
      parallel with ACE-Step music generation.
    - LuxTTS: ~1GB VRAM, 48kHz, 150x realtime on CPU (needs model download).
    """
    if not profile:
        profile = voicebox_create_preset_profile("DJ CryptoRadio RU", engine, voice_id, language)
    gen = _vb_call("POST", "/generate", {
        "profile_id": profile,
        "text": text,
        "language": language,
        "engine": engine,
        "model_size": "0.6B",
    })
    gid = gen.get("id") or gen.get("generation_id")
    if not gid:
        raise RuntimeError(f"Voicebox generate failed: {gen}")

    # poll status (SSE-formatted, possibly multi-line: 'data: {...}\n\ndata: {...}')
    t0 = time.time()
    audio_rel = None
    while time.time() - t0 < 300:
        st = _vb_call("GET", f"/generate/{gid}/status")
        payload = None
        if isinstance(st, str):
            # take the LAST data: line (latest state)
            for line in st.splitlines():
                if line.startswith("data:"):
                    try:
                        payload = json.loads(line[len("data:"):].strip())
                    except Exception:
                        pass
        elif isinstance(st, dict):
            payload = st
        status = payload.get("status") if isinstance(payload, dict) else None
        if status == "completed":
            rec = _vb_call("GET", "/history")
            items = rec.get("items") or []
            for it in items:
                if it.get("id") == gid:
                    audio_rel = it.get("audio_path")
                    break
            break
        if status in ("failed", "error"):
            raise RuntimeError(f"Voicebox generation failed: {payload}")
        time.sleep(1.5)

    if not audio_rel:
        raise RuntimeError("Voicebox task timed out")

    src = Path(os.environ.get("VOICEBOX_DATA_DIR", r"C:\Users\yusya\data")) / audio_rel
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, out_path)
    return out_path


# ---------------------------------------------------------------------------
# ffmpeg assembly helpers
# ---------------------------------------------------------------------------
def ff_duration(path: Path) -> float:
    """Get duration in seconds via ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    return float(out) if out else 0.0


def mix_voice_over_music(voice: Path, music: Path, out_path: Path,
                         music_volume: float = 0.22, tail: float = 1.2) -> Path:
    """Lay voice over music with ducking: music fades out under the voice,
    then holds ~1.2s of music tail at the end.

    Voice keeps full loudness; music is the bed.
    """
    vdur = ff_duration(voice)
    # music should be at least voice + tail; trim to that
    music_len = vdur + tail
    cmd = [
        FFMPEG, "-y",
        "-i", str(voice),
        "-i", str(music),
        "-filter_complex",
        f"[1:a]atrim=0:{music_len:.2f},volume={music_volume}[bed];"
        f"[bed]afade=t=out:st={vdur - 0.8:.2f}:d=0.8[bedf];"
        f"[0:a][bedf]amix=inputs=2:duration=first:dropout_transition=0[a]",
        "-map", "[a]",
        "-c:a", "libmp3lame", "-q:a", "2",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def concat_audio(files: list[Path], out_path: Path) -> Path:
    """Concatenate mp3s with silence pads in between (crossfade-free)."""
    tmpdir = Path(tempfile.mkdtemp(prefix="radio-concat-"))
    listfile = tmpdir / "files.txt"
    listfile.write_text("".join(f"file '{f.resolve()}'\n" for f in files))
    cmd = [
        FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", str(listfile),
        "-c:a", "libmp3lame", "-q:a", "2",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    shutil.rmtree(tmpdir, ignore_errors=True)
    return out_path


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------
def _bed_prompt(style: str | None, kind: str, seconds: int) -> str:
    """Build a music-bed prompt that MATCHES the current radio block's genre.

    style = genre of the block currently on air (e.g. 'dark psytrance 148bpm').
    The bed inherits that style but is subdued so the DJ voice stays on top.
    """
    if style:
        return (
            f"{style} — but as a quiet background music bed, subdued arrangement, "
            f"low volume, minimal elements, {seconds} seconds, instrumental, "
            f"does not overpower a voice-over, radio production bed"
        )
    # default genre-neutral fallback per content type
    defaults = {
        "jingle": "energetic radio station jingle, bright synth arpeggio, "
                  "uplifting electronic logo sting, punchy",
        "ad": "subtle commercial background music bed, soft electronic pad, "
              "professional, understated",
        "forecast": "calm ambient weather forecast music bed, soft piano and airy pads, relaxing",
        "newsfeed": "neutral news broadcast background music bed, minimal electronic pulse, "
                    "authoritative but calm",
    }
    return f"{defaults[kind]}, {seconds} seconds"


def wf_jingle(args) -> Path:
    """Station jingle: short music bed (in current block's style) + voice tag."""
    prompt = args.prompt or _bed_prompt(args.style, "jingle", JINGLE_SECONDS)
    music = ace_step_generate(prompt, JINGLE_SECONDS, args.tmp / "jingle_music.mp3",
                              seed=args.seed)
    if args.voice_text:
        voice = voicebox_speak(args.voice_text, args.tmp / "jingle_voice.mp3",
                               profile=args.profile)
        out = mix_voice_over_music(voice, music, args.out, music_volume=args.bed_volume)
    else:
        out = args.out
        shutil.copyfile(music, out)
    return out


def wf_ad(args) -> Path:
    """Radio ad: music bed in current block's style + commercial voice-over."""
    voice_text = args.voice_text or args.text
    if not voice_text:
        raise SystemExit("ad workflow needs --text or --voice-text (the ad copy)")
    prompt = args.prompt or _bed_prompt(args.style, "ad", AD_SECONDS)
    music = ace_step_generate(prompt, AD_SECONDS, args.tmp / "ad_music.mp3",
                              seed=args.seed)
    voice = voicebox_speak(voice_text, args.tmp / "ad_voice.mp3", profile=args.profile)
    return mix_voice_over_music(voice, music, args.out, music_volume=args.bed_volume)


def wf_forecast(args) -> Path:
    """Weather forecast: voice + light bed in current block's style."""
    voice_text = args.voice_text or args.text
    if not voice_text:
        raise SystemExit("forecast workflow needs --text or --voice-text (the forecast copy)")
    prompt = args.prompt or _bed_prompt(args.style, "forecast", FORECAST_SECONDS)
    music = ace_step_generate(prompt, FORECAST_SECONDS, args.tmp / "fc_music.mp3",
                              seed=args.seed)
    voice = voicebox_speak(voice_text, args.tmp / "fc_voice.mp3", profile=args.profile)
    return mix_voice_over_music(voice, music, args.out, music_volume=args.bed_volume)


def wf_newsfeed(args) -> Path:
    """News feed: headline voice-over + neutral bed in current block's style."""
    voice_text = args.voice_text or args.text
    if not voice_text:
        raise SystemExit("newsfeed workflow needs --text or --voice-text (the news copy)")
    prompt = args.prompt or _bed_prompt(args.style, "newsfeed", NEWS_SECONDS)
    music = ace_step_generate(prompt, NEWS_SECONDS, args.tmp / "news_music.mp3",
                              seed=args.seed)
    voice = voicebox_speak(voice_text, args.tmp / "news_voice.mp3", profile=args.profile)
    return mix_voice_over_music(voice, music, args.out, music_volume=args.bed_volume)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
WORKFLOWS = {
    "jingle": wf_jingle,
    "ad": wf_ad,
    "forecast": wf_forecast,
    "newsfeed": wf_newsfeed,
}


def main():
    p = argparse.ArgumentParser(description="AI-Radio content generation")
    sub = p.add_subparsers(dest="wf", required=True)

    for name in WORKFLOWS:
        sp = sub.add_parser(name)
        sp.add_argument("--text", help="copy/text (for ad/forecast/news)")
        sp.add_argument("--voice-text", help="voice-over text (defaults to --text)")
        sp.add_argument("--prompt", help="music bed prompt override")
        sp.add_argument("--style", help="genre of the CURRENT radio block, e.g. 'dark psytrance 148bpm' "
                                        "-- the bed inherits this style (quiet, under the voice)")
        sp.add_argument("--bed-volume", type=float, default=0.22,
                        help="background music volume under voice (0..1, default 0.22)")
        sp.add_argument("--out", type=Path, default=None, help="output mp3 path")
        sp.add_argument("--seed", type=int, default=None, help="music seed for reproducibility")
        sp.add_argument("--profile", default=None, help="Voicebox voice profile id")
        sp.add_argument("--keep-tmp", action="store_true", help="keep temp files")

    args = p.parse_args()
    base_out = Path("out") / f"{args.wf}_{int(time.time())}.mp3"
    args.out = (args.out or base_out).resolve()
    args.tmp = Path(tempfile.mkdtemp(prefix=f"radio-{args.wf}-"))

    t0 = time.time()
    out = WORKFLOWS[args.wf](args)
    dt = time.time() - t0
    print(f"OK {args.wf}: {out}  ({dt:.1f}s, {ff_duration(out):.1f}s audio)")
    if not args.keep_tmp:
        shutil.rmtree(args.tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
