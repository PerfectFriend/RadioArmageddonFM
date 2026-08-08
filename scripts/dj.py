#!/usr/bin/env python3
"""
Master-FM: DJ agent.

Builds playlist from cache folders per schedule, mixes via ffmpeg
into continuous MP3 stream and serves via HTTP (http://localhost:8090/radio).

Ring buffer: listeners connect at any moment and hear
stream with ~5 sec delay from current position - like real radio.
"""
import os
import random
import socket
import subprocess
import threading
import time
import glob
import yaml

RADIO_ROOT = r"C:\Users\tomas\ai-radio"
CACHE = os.path.join(RADIO_ROOT, "cache")
PORT = 8090
MOUNT = "/radio"
RING_SECONDS = 5          # stream delay for new listeners
CHUNK = 4096

# ---------------------------------------------------------------- config
def load_config():
    with open(os.path.join(RADIO_ROOT, "config.yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["radio"]

CONFIG = load_config()

def is_night_mode():
    """True if currently night batch (20:00-07:00)."""
    hour = time.localtime().tm_hour
    night = CONFIG["modes"]["night_batch"]
    if not night["enabled"]:
        return False
    start = night["start_hour"]
    end = night["end_hour"]
    # night interval crosses midnight
    if start > end:
        return hour >= start or hour < end
    return start <= hour < end

def is_day_mode():
    """True if currently day mode (07:00-20:00)."""
    return not is_night_mode()

def list_files(folder):
    """All audio in folder (wav/mp3/ogg)."""
    out = []
    for ext in ("*.wav", "*.mp3", "*.ogg", "*.flac"):
        out.extend(glob.glob(os.path.join(folder, ext)))
    return sorted(out)

def pick_one(folder):
    files = list_files(folder)
    return random.choice(files) if files else None

# ---------------------------------------------------------------- playlist
def build_playlist(now=None):
    """Builds hour of air: jingle -> music -> news -> ads.
    Considers mode: night - full set, day - only from cache.
    """
    now = now or time.localtime()
    hour = now.tm_hour
    items = []  # (type, path)

    def add_jingle(theme):
        p = pick_one(os.path.join(CACHE, "jingles", theme))
        if p: items.append(("jingle", p))

    night_mode = is_night_mode()

    # Intro jingle
    add_jingle("morning" if 6 <= hour < 12 else "funny")

    # Music blocks with jingles every N tracks
    styles = [d for d in os.listdir(os.path.join(CACHE, "music"))
              if os.path.isdir(os.path.join(CACHE, "music", d))]
    if not styles:
        styles = ["ambient"]
    random.shuffle(styles)

    tracks_since_jingle = 0
    for style in styles:
        p = pick_one(os.path.join(CACHE, "music", style))
        if not p:
            continue
        items.append(("music", p))
        tracks_since_jingle += 1
        if tracks_since_jingle >= CONFIG["schedule"]["jingle_every_tracks"]:
            add_jingle(random.choice(["traffic", "funny"]))
            tracks_since_jingle = 0

    # News
    if night_mode:
        # Night: all categories, more news
        cats = list(CONFIG["sources"]["news_categories"].keys())
        for cat in cats:
            p = pick_one(os.path.join(CACHE, "news", cat))
            if p:
                items.append(("news", p))
    else:
        # Day: only breaking news (check for fresh)
        cats = list(CONFIG["sources"]["news_categories"].keys())
        for cat in random.sample(cats, min(2, len(cats))):
            p = pick_one(os.path.join(CACHE, "news", cat))
            if p:
                items.append(("news", p))

    # Ads
    ad_count = 3 if night_mode else 2
    for _ in range(ad_count):
        p = pick_one(os.path.join(CACHE, "ads"))
        if p:
            items.append(("ad", p))

    # Audiobooks at night
    if hour in CONFIG["schedule"]["audiobook_at_hours"]:
        p = pick_one(os.path.join(CACHE, "audiobooks"))
        if p:
            items.append(("audiobook", p))

    return items

def write_concat_list(items, path):
    """List for ffmpeg concat. Playlist loops: -stream_loop -1."""
    with open(path, "w", encoding="utf-8") as f:
        for _, p in items:
            f.write(f"file '{p.replace(chr(39), chr(39)*2)}'\n")

# ---------------------------------------------------------------- MP3 header generator
# Use pre-generated valid header from ffmpeg (silence_header.mp3)
# Contains: ID3v2.4 + silence frames (500ms)
# Generated once: ffmpeg -f lavfi -i anullsrc=r=44100:cl=stereo -t 0.5 -c:a libmp3lame -b:a 128k -f mp3 silence_header.mp3

def load_mp3_header():
    """Loads pre-generated valid MP3 header with silence."""
    header_path = os.path.join(RADIO_ROOT, "silence_header.mp3")
    if os.path.exists(header_path):
        with open(header_path, "rb") as f:
            header = f.read()
            print(f"[dj] Loaded MP3 header from file: {len(header)} bytes")
            return header
    else:
        # Fallback: minimal ID3 + empty frame
        print("[dj] Warning: silence_header.mp3 not found, using fallback header")
        return b'ID3\x04\x00\x00\x00\x00\x00\x00\xff\xfb\x90\x00'



# ---------------------------------------------------------------- stream
class RingBuffer:
    """Ring buffer for last N seconds of stream."""
    def __init__(self, seconds, sample_rate=44100, channels=2):
        self.buf = bytearray()
        self.max_bytes = seconds * sample_rate * channels * 2  # 16-bit
        self.lock = threading.Lock()

    def write(self, data: bytes):
        with self.lock:
            self.buf.extend(data)
            if len(self.buf) > self.max_bytes:
                del self.buf[: len(self.buf) - self.max_bytes]

    def snapshot(self) -> bytes:
        with self.lock:
            return bytes(self.buf)

    def find_frame_sync(self, start_offset=0):
        """Finds nearest MP3 frame sync (0xFFE0/0xFFF0) after start_offset.
        Returns offset or -1 if not found.
        """
        with self.lock:
            data = self.buf
            for i in range(start_offset, len(self.buf) - 1):
                if data[i] == 0xFF and (data[i+1] & 0xE0) == 0xE0:
                    return i
            return -1


class RadioServer:
    def __init__(self):
        self.ring = RingBuffer(RING_SECONDS)
        self.ffmpeg = None
        self.running = True
        # Load valid header from file (generated by ffmpeg)
        self.cached_header = load_mp3_header()
        print(f"[dj] Pre-loaded MP3 header: {len(self.cached_header)} bytes")

    def start_ffmpeg(self, concat_file: str):
        """Starts main ffmpeg for streaming with mastering chain."""
        print("[dj] Starting main ffmpeg for streaming with mastering chain...")
        
        # Professional mastering chain:
        # 1. highpass 30Hz - remove sub-bass
        # 2. agate (gate) - noise gate (threshold in [0,1] range)
        # 3. equalizer - gentle EQ (highpass + tilt + side boost)
        # 4. loudnorm (leveler) - target loudness in LUFS
        # 5. compand (multiband compressor) - gentle mid-side compression
        # 6. alimiter (limiter) - soft limiting
        # 7. alimiter (brickwall) - hard ceiling limiting
        
        mastering_filters = (
                    "highpass=f=30,"                    # 1. Highpass 30Hz
                    "agate=threshold=0.001:ratio=10:attack=10:release=100,"  # 2. Gate (threshold 0-1)
                    "equalizer=f=100:width_type=h:width=200:gain=2,"       # 3a. Tilt EQ boost high
                    "equalizer=f=5000:width_type=h:width=5000:gain=1.5,"   # 3b. Presence boost
                    "stereowiden=1.2,"                # 3c. Stereo widen
                    "loudnorm=I=-14:TP=-1:LRA=11:print_format=summary:measured_I=-20:measured_TP=-6:measured_LRA=2:measured_thresh=-30:offset=0.5:linear=true:dual_mono=false,"    # 4. Leveler (target -14 LUFS)
                    "volume=6dB,"                     # Makeup gain before limiters
                    "alimiter=limit=0.89:attack=5:release=50:asc=1:asc_level=0.5,"  # 6. Limiter (limit 0-1, asc_level 0-1)
                    "alimiter=limit=0.94:attack=0.1:release=5:asc=1"       # 7. Brickwall (limit 0-1, -0.5dB approx 0.94)
                )
      
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-stream_loop", "-1",
            "-f", "concat", "-safe", "0", "-i", concat_file,
            "-af", mastering_filters,
            "-ar", str(CONFIG["sample_rate"]),
            "-b:a", f"{CONFIG['bitrate']}k",
            "-f", "mp3", "pipe:1",
        ]
        self.ffmpeg = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        def pump():
            while self.running and self.ffmpeg and self.ffmpeg.poll() is None:
                data = self.ffmpeg.stdout.read(CHUNK)
                if not data:
                    break
                self.ring.write(data)
            print("[dj] ffmpeg stream stopped")
        threading.Thread(target=pump, daemon=True).start()

    def handle(self, conn):
        """Serve stream to listener: valid header + stream from frame boundary."""
        try:
            conn.sendall(b"HTTP/1.1 200 OK\r\n"
                         b"Content-Type: audio/mpeg\r\n"
                         b"Cache-Control: no-cache\r\n"
                         b"Connection: close\r\n\r\n")
          
            # 1. Send valid MP3 header (ID3 + silence) for proper decoder start
            # Use sendall for guaranteed full header delivery
            conn.sendall(self.cached_header)
          
            # 2. Find frame sync in buffer and stream from there
            snap = self.ring.snapshot()
            sync_offset = self.ring.find_frame_sync(0)
            if sync_offset == -1:
                # Fallback: if sync not found, send whole buffer as-is
                if snap:
                    conn.sendall(snap)
            else:
                # Send buffer from frame boundary
                conn.sendall(snap[sync_offset:])
          
            # 3. Live stream from buffer
            last_len = len(snap)
            while self.running:
                snap = self.ring.snapshot()
                if len(snap) > last_len:
                    new_data = snap[last_len:]
                    conn.sendall(new_data)
                    last_len = len(snap)
                time.sleep(0.1)
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"[dj] Connection error: {e}")
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def serve(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", PORT))
        srv.listen(5)
        print(f"[dj] Master-FM listening http://localhost:{PORT}{MOUNT}")
        while self.running:
            try:
                conn, _ = srv.accept()
            except OSError:
                break
            threading.Thread(target=self.handle, args=(conn,), daemon=True).start()


def main():
    print("[dj] Master-FM starting...")
    items = build_playlist()
    if not items:
        print("[dj] Cache empty! Populate first: gen_music.py + gen_voice_content.py")
        return

    labels = [t for t, _ in items]
    print(f"[dj] Playlist ({len(items)} blocks): {labels}")

    concat_file = os.path.join(RADIO_ROOT, "playlist.txt")
    write_concat_list(items, concat_file)

    server = RadioServer()
    server.start_ffmpeg(concat_file)

    # Wait for first data in buffer
    time.sleep(3)
    print(f"[dj] On air! Listen: http://localhost:{PORT}{MOUNT}")

    server.serve()


if __name__ == "__main__":
    main()