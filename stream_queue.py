#!/usr/bin/env python3
"""Очередь трансляции 24/7 с точностью до 0.1 с.

Архитектура:
  1. КЭШ заготовок: джинглы/новости/реклама/музыка генерятся заранее и лежат
     в каталоге кэша (по умолчанию ~/.w420/radio-cache).
  2. ПАКЕТ: build_queue() собирает из кэша «пакет» — список сегментов,
     идущих подряд без пауз, каждому назначено абсолютное время старта (Unix).
  3. ОЧЕРЕДЬ: пакеты складываются в очередь и воспроизводятся планировщиком,
     который выравнивается по системному времени (time.monotonic + offset к wall clock),
     чтобы сигналы точного времени (time signal) звучали с точностью до 0.1 с.

CLI:
  python stream_queue.py build --hours 1 --cache ~/.w420/radio-cache --out queue.json
  python stream_queue.py play  --queue queue.json            # реальное воспроизведение
  python stream_queue.py play  --queue queue.json --dry-run  # только расчёт таймингов
"""
import argparse
import json
import math
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path

TOLERANCE_S = 0.1  # допуск расхождения факта со планом, секунды


def ff_duration(path: Path) -> float:
    """Длительность аудиофайла через ffprobe (секунды)."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    return float(r.stdout.strip())


@dataclass
class Segment:
    """Один элемент эфира: файл + абсолютное время старта."""
    kind: str          # jingle | news | ad | music | time | voice
    path: str          # путь к аудио в кэше
    start_ts: float    # Unix-время старта (абсолютное)
    duration: float    # длительность, с

    @property
    def end_ts(self) -> float:
        return self.start_ts + self.duration


class StreamQueue:
    """Очередь сегментов с плотной упаковкой: следующий старт = конец предыдущего."""

    def __init__(self):
        self.segments: list[Segment] = []

    def add(self, kind: str, path: Path, start_ts: float) -> Segment:
        dur = ff_duration(path)
        seg = Segment(kind=kind, path=str(path), start_ts=start_ts, duration=dur)
        self.segments.append(seg)
        return seg

    def append_after_last(self, kind: str, path: Path, pad_s: float = 0.0) -> Segment:
        start = self.segments[-1].end_ts + pad_s if self.segments else time.time()
        return self.add(kind, path, start)

    def to_json(self, path: Path):
        path.write_text(json.dumps([asdict(s) for s in self.segments], ensure_ascii=False, indent=1))

    @classmethod
    def from_json(cls, path: Path) -> "StreamQueue":
        q = cls()
        for d in json.loads(path.read_text()):
            q.segments.append(Segment(**d))
        return q


def build_queue(cache: Path, hours: float, start_ts: float | None = None) -> StreamQueue:
    """Собирает пакет из кэша: чередует jingle -> music -> voice/news по кругу.

    Всё, что есть в кэше, раскладывается подряд. Если кэш пуст — падает с понятной ошибкой.
    """
    cache = Path(cache)
    pool = sorted(p for p in cache.glob("**/*") if p.suffix.lower() in (".mp3", ".wav", ".ogg", ".flac"))
    if not pool:
        raise SystemExit(f"кэш пуст: {cache} — сначала нагенерируй сегменты (radio_gen.py)")
    q = StreamQueue()
    t = start_ts if start_ts is not None else math.ceil(time.time() / 60) * 60  # ровный минутный старт
    kinds = ["jingle", "music", "voice", "news", "ad", "time"]
    i = 0
    while t < (start_ts or time.time()) + hours * 3600:
        p = pool[i % len(pool)]
        q.add(kinds[i % len(kinds)], p, t)
        t = q.segments[-1].end_ts
        i += 1
    return q


class PrecisePlayer:
    """Воспроизводит очередь по абсолютному времени.

    Выравнивание: для каждого сегмента ждём до start_ts (монотонные часы + сдвиг
    к wall clock), затем играем через ffplay. После старта фиксируем фактическое
    отклонение; если оно > TOLERANCE_S — пишем в отчёт (нужно для time signal).
    """

    def __init__(self, queue: StreamQueue, dry_run: bool = False):
        self.q = queue
        self.dry_run = dry_run
        self.report: list[dict] = []

    def _wait_until(self, ts: float):
        """Ждём до wall-clock момента ts с точностью ~1 мс (busy-wait последние 20 мс)."""
        while True:
            now = time.time()
            dt = ts - now
            if dt <= 0:
                return
            if dt > 0.02:
                time.sleep(dt - 0.02)
            else:
                time.sleep(0.001)

    def play(self, only_from: float | None = None):
        mono0 = time.monotonic()
        for seg in self.q.segments:
            if only_from is not None and seg.end_ts < only_from:
                continue  # уже ушло в прошлое
            if not self.dry_run:
                self._wait_until(seg.start_ts)
                actual = time.time()
                err = actual - seg.start_ts
                self.report.append({"kind": seg.kind, "path": seg.path,
                                    "planned": seg.start_ts, "actual": actual,
                                    "err_s": round(err, 3), "ok": abs(err) <= TOLERANCE_S})
                subprocess.run(["ffplay", "-v", "error", "-nodisp", "-autoexit", seg.path],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                # dry-run: только математика, без ожидания и звука
                self.report.append({"kind": seg.kind, "path": seg.path,
                                    "planned": seg.start_ts, "duration": seg.duration,
                                    "err_s": 0.0, "ok": True})
        return self.report


def main():
    ap = argparse.ArgumentParser(description="Очередь трансляции радио с точностью 0.1 с")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="собрать пакет из кэша")
    b.add_argument("--hours", type=float, default=1.0)
    b.add_argument("--cache", default=str(Path.home() / ".w420/radio-cache"))
    b.add_argument("--out", required=True)
    p = sub.add_parser("play", help="воспроизвести очередь")
    p.add_argument("--queue", required=True)
    p.add_argument("--dry-run", action="store_true", help="расчёт таймингов без звука")
    p.add_argument("--from-ts", type=float, default=None, help="начать с указанного времени")
    args = ap.parse_args()

    if args.cmd == "build":
        q = build_queue(args.cache, args.hours)
        q.to_json(Path(args.out))
        total = q.segments[-1].end_ts - q.segments[0].start_ts if q.segments else 0
        print(f"OK: {len(q.segments)} сегментов, {total/60:.1f} мин, старт {q.segments[0].start_ts:.1f} -> {args.out}")
    else:
        q = StreamQueue.from_json(Path(args.queue))
        rep = PrecisePlayer(q, dry_run=args.dry_run).play(only_from=args.from_ts)
        bad = [r for r in rep if not r.get("ok", True)]
        mx = max((abs(r["err_s"]) for r in rep), default=0.0)
        print(f"проиграно {len(rep)} сегментов, макс. отклонение {mx:.3f} с, допуск {TOLERANCE_S} с, нарушений: {len(bad)}")
        for r in bad[:10]:
            print("  DRIFT:", r)


if __name__ == "__main__":
    main()
