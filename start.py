#!/usr/bin/env python
"""
RadioArmageddonFM - Quick start launcher.
Starts ACE-Step API, Voicebox TTS, and pipeline services (scraper, buffer, scheduler, streamer).
"""
import subprocess
import sys
import time
import os
import signal
import threading
from pathlib import Path

ACE_STEP_DIR = Path(os.environ.get("ACE_STEP_DIR", r"C:\Users\yusya\ACE-Step-1.5"))
ACE_STEP_VENV_PY = ACE_STEP_DIR / ".venv" / "Scripts" / "python.exe"
VOICEBOX_EXE = Path(r"C:\Program Files\Voicebox\voicebox-server.exe")
REPO_ROOT = Path(__file__).parent


def check_prereqs():
    """Verify all prerequisites are in place."""
    print("🔍 Checking prerequisites...")
    
    ok = True
    if not ACE_STEP_VENV_PY.exists():
        print(f"  ❌ ACE-Step venv python not found: {ACE_STEP_VENV_PY}")
        ok = False
    else:
        print(f"  ✅ ACE-Step: {ACE_STEP_VENV_PY}")
    
    if not VOICEBOX_EXE.exists():
        print(f"  ❌ Voicebox server not found: {VOICEBOX_EXE}")
        ok = False
    else:
        print(f"  ✅ Voicebox: {VOICEBOX_EXE}")
    
    if not shutil.which("ffmpeg"):
        print("  ❌ ffmpeg not in PATH")
        ok = False
    else:
        print(f"  ✅ ffmpeg: {shutil.which('ffmpeg')}")
    
    return ok


def start_service(name: str, cmd: list, cwd: Path, health_url: str = None, 
                  health_check=None, max_wait: int = 60) -> subprocess.Popen:
    """Generic service starter with health check."""
    print(f"\n🚀 Starting {name}...")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    
    if health_url:
        import urllib.request
        import json
        for i in range(max_wait // 2):
            try:
                with urllib.request.urlopen(health_url, timeout=3) as resp:
                    data = json.loads(resp.read())
                    if health_check(data):
                        print(f"  ✅ {name} UP (pid={proc.pid})")
                        return proc
            except Exception:
                pass
            time.sleep(2)
            print(f"  ⏳ Waiting {name}... ({i+1}/{max_wait//2})")
    else:
        # No health check - give it a moment to start
        time.sleep(3)
        if proc.poll() is None:
            print(f"  ✅ {name} started (pid={proc.pid})")
            return proc
        else:
            stderr = proc.stderr.read() if proc.stderr else b""
            raise RuntimeError(f"{name} failed to start: {stderr.decode()[:200]}")
    
    proc.terminate()
    raise RuntimeError(f"{name} failed to start within {max_wait}s")


def start_ace_step():
    """Start ACE-Step API server."""
    return start_service(
        "ACE-Step API",
        [str(ACE_STEP_VENV_PY), "-m", "acestep.api_server", "--host", "0.0.0.0", "--port", "8001"],
        ACE_STEP_DIR,
        health_url="http://127.0.0.1:8001/health",
        health_check=lambda d: d.get("data", {}).get("status") == "ok",
        max_wait=120
    )


def start_voicebox():
    """Start Voicebox TTS server."""
    return start_service(
        "Voicebox TTS",
        [str(VOICEBOX_EXE), "--host", "127.0.0.1", "--port", "7860"],
        REPO_ROOT,
        health_url="http://127.0.0.1:7860/health",
        health_check=lambda d: d.get("status") == "healthy",
        max_wait=60
    )


def start_pipeline_service(name: str, module_path: str) -> subprocess.Popen | None:
    """Start a pipeline daemon (scraper, buffer, scheduler, streamer) if it exists."""
    run_py = REPO_ROOT / module_path / "run.py"
    if not run_py.exists():
        print(f"  ⏭️  {name} not found ({run_py}), skipping")
        return None
    
    print(f"\n🚀 Starting {name}...")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    
    proc = subprocess.Popen(
        [sys.executable, "run.py"],
        cwd=str(REPO_ROOT / module_path),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    
    # Start log reader thread
    def log_reader():
        for line in proc.stdout:
            print(f"  [{name}] {line.rstrip()}")
    
    threading.Thread(target=log_reader, daemon=True).start()
    
    time.sleep(2)
    if proc.poll() is None:
        print(f"  ✅ {name} started (pid={proc.pid})")
        return proc
    else:
        print(f"  ❌ {name} failed to start")
        return None


def run_demo():
    """Run a quick demo generation."""
    print("\n🎬 Running demo generation...")
    result = subprocess.run([
        sys.executable, "radio_gen.py", "jingle",
        "--voice-text", "Вы слушаете Radio Armageddon FM! Хаос на всех волнах.",
        "--style", "dark psytrance 148bpm",
        "--out", "out/demo_jingle.mp3"
    ], capture_output=True, text=True, timeout=180)
    
    if result.returncode == 0:
        print(f"  ✅ Demo generated!")
        print(f"  {result.stdout.strip()}")
    else:
        print(f"  ❌ Demo failed:")
        print(f"  {result.stderr}")


def signal_handler(signum, frame):
    raise KeyboardInterrupt()


if __name__ == "__main__":
    import shutil
    
    print("=" * 60)
    print("  RadioArmageddonFM — Full Pipeline Start")
    print("=" * 60)
    
    if not check_prereqs():
        print("\n❌ Prerequisites missing. See README.md for setup.")
        sys.exit(1)
    
    # Install signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    procs = {}
    
    try:
        # Core services
        procs["ace_step"] = start_ace_step()
        procs["voicebox"] = start_voicebox()
        
        # Pipeline services (optional - will be added when you push from other machine)
        procs["scraper"] = start_pipeline_service("News Scraper", "scraper")
        procs["buffer"] = start_pipeline_service("Text Buffer", "buffer")
        procs["scheduler"] = start_pipeline_service("Stream Scheduler", "scheduler")
        procs["streamer"] = start_pipeline_service("Streamer", "streamer")
        
        run_demo()
        
        print("\n" + "=" * 60)
        print("  🎉 All available services running! Press Ctrl+C to stop.")
        print("  ACE-Step:   http://127.0.0.1:8001")
        print("  Voicebox:   http://127.0.0.1:7860")
        if procs.get("scraper"): print("  Scraper:    buffer/incoming.jsonl")
        if procs.get("buffer"): print("  Buffer:     buffer/selected.jsonl")
        if procs.get("scheduler"): print("  Scheduler:  stream/playlist.json")
        if procs.get("streamer"): print("  Streamer:   Icecast source")
        print("=" * 60)
        
        # Keep running
        while True:
            # Check for dead processes
            for name, proc in list(procs.items()):
                if proc and proc.poll() is not None:
                    print(f"\n  ⚠️  {name} died (exit={proc.returncode}), restarting...")
                    # Could add restart logic here
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down...")
    finally:
        for name, proc in procs.items():
            if proc:
                print(f"  Stopping {name}...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        print("  ✅ Clean shutdown complete.")