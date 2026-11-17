#!/usr/bin/env python3
"""Сборка джингла по ТЗ пользователя:

- общая длина T = 2 × длина голоса (музыка в 2 раза длиннее текста);
- SFX ДО текста (райзер, 1 бар) и ПОСЛЕ текста (импакт, 1 бар) — на BPM-сетке;
- музыка идёт на всю длину T, громко (ducking под голосом мягкий, -4 дБ);
- единый ритм: всё квантовано к бару BPM beds.

Запуск: python3 jingle_build.py <emotion> <voice.wav> <out.mp3>
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import radio_gen as rg

# emo -> (промпт ACE-Step, bpm)
BEDS = {
    "angry":    ("dark aggressive techno jingle, pounding distorted kick on every beat, "
                 "distorted bass, minor key, heavy, loud, punchy, 150 bpm, instrumental, "
                 "full mix radio jingle", 150),
    "cheerful": ("upbeat funky house jingle, bright piano chords, handclaps on 2 and 4, "
                 "bouncy bass, major key, sunny, loud, punchy, 124 bpm, instrumental", 124),
    "calm":     ("chill downtempo ambient jingle, warm soft pads, gentle piano, "
                 "relaxed groove, major key, 90 bpm, instrumental, medium volume", 90),
    "hype":     ("driving psytrance jingle, rolling bassline, bright leads, energetic, "
                 "festival sound, loud, punchy, 148 bpm, instrumental", 148),
}


def sh(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def _write_wav(path: Path, data: "np.ndarray", sr: int = 44100):
    import soundfile as sf
    sf.write(str(path), data.astype("float32"), sr)


def sfx_riser(path: Path, bar: float, sr: int = 44100):
    """Райзер 1 бар: шумовая лента с растущей полосой (через FFT-фильтрацию) + синус вверх."""
    import numpy as np
    n = int(bar * sr)
    t = np.arange(n) / sr
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(n)
    # полосовая фильтрация с растущей центральной частотой (короткие окна)
    out = np.zeros(n)
    win = int(0.02 * sr)
    from numpy.fft import rfft, irfft
    for i in range(0, n - win, win // 2):
        seg = noise[i:i + win] * np.hanning(win)
        sp = rfft(seg)
        f0 = 300 + 6000 * (i / n)
        freqs = np.fft.rfftfreq(win, 1 / sr)
        sp *= np.exp(-((freqs - f0) ** 2) / (2 * (max(150, f0 * 0.4)) ** 2))
        out[i:i + win] += irfft(sp, win) * np.hanning(win)
    sweep = 0.5 * np.sin(2 * np.pi * (150 * t + 300 * t * t / bar))
    bass = 0.35 * np.sin(2 * np.pi * 55 * t)
    sig = (out * 0.5 + sweep + bass)
    env = np.minimum(1, t / (bar * 0.05)) * np.clip((bar - t) / (bar * 0.2), 0, 1)
    _write_wav(path, sig * env * 1.2, sr)


def sfx_impact(path: Path, bar: float, sr: int = 44100):
    """Импакт: синус вниз 160->40 Гц + шумовой всплеск + эхо-хвост."""
    import numpy as np
    d = min(bar, 1.2)
    n = int(d * sr)
    t = np.arange(n) / sr
    kick = 0.9 * np.sin(2 * np.pi * (160 * np.exp(-3 * t / d) + 40) * t) * np.exp(-2.5 * t / d)
    noise = np.random.default_rng(11).standard_normal(n) * np.exp(-8 * t / d) * 0.5
    sig = kick + noise
    # простое эхо
    ech = np.zeros_like(sig)
    dl = int(0.06 * sr)
    ech[dl:] += sig[:-dl] * 0.5
    sig = sig + ech
    _write_wav(path, sig * 1.5, sr)


def build(emo: str, voice_wav: Path, out_mp3: Path):
    prompt, bpm = BEDS[emo]
    vdur = rg.ff_duration(voice_wav)
    bar = 60.0 / bpm * 4          # 1 бар = 4 бита
    total = 2.0 * vdur            # ТЗ: музыка в 2 раза длиннее текста
    total = max(total, vdur + 2 * bar + 0.5)
    voice_at = bar                # голос вступает после интрارك (1 бар)
    outro_at = total - bar        # импакт на последнем баре

    tmp = Path("/tmp/jingle_build"); tmp.mkdir(exist_ok=True)
    bed = tmp / f"bed_{emo}.mp3"
    rg.ace_step_generate(prompt, round(total), bed, seed=4200 + hash(emo) % 100,
                         audio_format="mp3", bpm=bpm)
    riser = tmp / "riser.wav"; sfx_riser(riser, bar)
    impact = tmp / "impact.wav"; sfx_impact(impact, bar)

    out_tmp = tmp / f"mix_{emo}.wav"
    fc = (
        f"[1:a]atrim=0:{total:.3f},aresample=44100,asetpts=PTS-STARTPTS[bed];"
        # мягкий ducking под голосом: музыка уходит на -4 дБ, быстро отпускает
        f"[2:a]aresample=44100,adelay={int(voice_at*1000)}|{int(voice_at*1000)}[vox];"
        f"[bed][vox]sidechaincompress=threshold=0.02:ratio=3:attack=10:release=250[bedd];"
        f"[3:a]aresample=44100,anull[intr];"
        f"[4:a]aresample=44100,adelay={int(outro_at*1000)}|{int(outro_at*1000)}[outr];"
        f"[bedd][intr][vox][outr]amix=inputs=4:duration=first:normalize=0,"
        f"loudnorm=I=-14:TP=-1.5[aout]"
    )
    sh(["ffmpeg", "-y", "-v", "error",
        "-i", str(bed), "-i", str(bed), "-i", str(voice_wav),
        "-i", str(riser), "-i", str(impact),
        "-filter_complex", fc, "-map", "[aout]",
        "-t", f"{total:.3f}", "-c:a", "pcm_s16le", str(out_tmp)])
    sh(["ffmpeg", "-y", "-v", "error", "-i", str(out_tmp),
        "-c:a", "libmp3lame", "-b:a", "192k", str(out_mp3)])
    ogg = out_mp3.with_suffix(".ogg")
    sh(["ffmpeg", "-y", "-v", "error", "-i", str(out_mp3), "-c:a", "libopus", str(ogg)])
    print(f"JINGLE {emo}: voice={vdur:.1f}s total={total:.1f}s bar={bar:.2f}s -> {out_mp3}")


if __name__ == "__main__":
    build(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]))
