#!/usr/bin/env python
"""
RadioArmageddonFM - Quick start launcher.
Starts both ACE-Step API and Voicebox servers, then runs a demo generation.
"""
import subprocess
import sys
import time
import os
from pathlib import Path

ACE_STEP_DIR = Path(os.environ.get("ACE_STEP_DIR", r"C:\Users\yusya\ACE-Step-1.5"))
ACE_STEP_VENV_PY = ACE_STEP_DIR / ".venv" / "Scripts" / "python.exe"
VOICEBOX_EXE = Path(r"C:\Program Files\Voicebox\voicebox-server.exe")


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


def start_ace_step():
    """Start ACE-Step API server."""
    print("\n🚀 Starting ACE-Step API server...")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    
    proc = subprocess.Popen(
        [str(ACE_STEP_VENV_PY), "-m", "acestep.api_server", "--host", "0.0.0.0", "--port", "8001"],
        cwd=str(ACE_STEP_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    
    # Wait for health
    import urllib.request
    import json
    for i in range(30):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=3) as resp:
                data = json.loads(resp.read())
                if data.get("data", {}).get("status") == "ok":
                    print(f"  ✅ ACE-Step UP (pid={proc.pid})")
                    return proc
        except Exception:
            pass
        time.sleep(2)
        print(f"  ⏳ Waiting... ({i+1}/30)")
    
    proc.terminate()
    raise RuntimeError("ACE-Step failed to start")


def start_voicebox():
    """Start Voicebox TTS server."""
    print("\n🎙️ Starting Voicebox TTS server...")
    proc = subprocess.Popen(
        [str(VOICEBOX_EXE), "--host", "127.0.0.1", "--port", "7860"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    
    import urllib.request
    import json
    for i in range(30):
        try:
            with urllib.request.urlopen("http://127.0.0.1:7860/health", timeout=3) as resp:
                data = json.loads(resp.read())
                if data.get("status") == "healthy":
                    print(f"  ✅ Voicebox UP (pid={proc.pid})")
                    return proc
        except Exception:
            pass
        time.sleep(2)
        print(f"  ⏳ Waiting... ({i+1}/30)")
    
    proc.terminate()
    raise RuntimeError("Voicebox failed to start")


def run_demo():
    """Run a quick demo generation."""
    print("\n🎬 Running demo generation...")
    import subprocess
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


if __name__ == "__main__":
    import shutil
    
    print("=" * 60)
    print("  RadioArmageddonFM — Quick Start")
    print("=" * 60)
    
    if not check_prereqs():
        print("\n❌ Prerequisites missing. See README.md for setup.")
        sys.exit(1)
    
    ace_proc = None
    vb_proc = None
    
    try:
        ace_proc = start_ace_step()
        vb_proc = start_voicebox()
        
        run_demo()
        
        print("\n" + "=" * 60)
        print("  🎉 All services running! Press Ctrl+C to stop.")
        print("  ACE-Step:  http://127.0.0.1:8001")
        print("  Voicebox:  http://127.0.0.1:7860")
        print("=" * 60)
        
        # Keep running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down...")
    finally:
        for proc in [ace_proc, vb_proc]:
            if proc:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        print("  ✅ Clean shutdown complete.")