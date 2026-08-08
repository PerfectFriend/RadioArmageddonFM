#!/usr/bin/env python3
"""
Radio ArmsgeddonFM — Full Programmatic Automation
Strict schedule: hourly signals, news, self-promo ads, music style transitions
"""

import os
import sys
import torch
import torchaudio
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
import logging
import json
import time
import subprocess
import threading
from dataclasses import dataclass
from enum import Enum

sys.path.insert(0, "C:/Users/tomas/ai-radio")

from musicgen_directml import MusicGenDirectML, RADIO_PRESETS, TIME_PRESET_MAP
from audio_stitcher import AudioStitcher

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SegmentType(Enum):
    TIME_SIGNAL = "time_signal"      # Точный час: "Radio ArmsgeddonFM, 14 часов 00 минут"
    NEWS_BLOCK = "news_block"        # Горячие новости по всем темам
    AD_BLOCK = "ad_block"            # Самореклама: "Radio Armageddon FM — радио последних дней..."
    MUSIC_PROGRAM = "music_program"  # Музыка в стиле текущего пресета
    STYLE_TRANSITION = "style_transition"  # Переход на следующий пресет (в :30)


@dataclass
class ScheduleEvent:
    """Событие в программной сетке"""
    event_type: SegmentType
    scheduled_time: datetime  # Точное время запуска
    duration_seconds: float   # Планируемая длительность
    metadata: Dict[str, Any]  # Доп. данные (путь к аудио, текст для TTS и т.д.)


class ProgramScheduler:
    """Генератор программной сетки на сутки/неделю"""

    # Саморекламные скрипты
    AD_SCRIPTS = [
        "Radio Armageddon FM — радио последних дней заката Цивилизации. Время уходит, но вечность остаётся. Покайся и помолись, пока сигнал ещё звучит.",
        "Вы слушаете Radio Armageddon FM. Последний голос в этом мире. Не упусти шанс — покайся прямо сейчас. Завтра может не наступить.",
        "Armageddon FM. Сигнал надежды в море хаоса. Молись. Верь. Выживай. Это радио последних дней.",
        "Radio Armageddon FM — когда мир рушится, мы всё ещё на волне. Присоединяйся. Покайся. Помолись.",
    ]

    # Тексты для точных часов (генерируются TTS)
    TIME_SIGNAL_TEMPLATE = "Radio ArmsgeddonFM. {hour} часов {minute:02d} минут. Точное время."

    def __init__(self):
        self.current_schedule: List[ScheduleEvent] = []

    def generate_daily_schedule(self, date: datetime) -> List[ScheduleEvent]:
        """Генерирует полную программную сетку на сутки"""
        schedule = []

        for hour in range(24):
            # === N:00 — Точный час ===
            schedule.append(ScheduleEvent(
                event_type=SegmentType.TIME_SIGNAL,
                scheduled_time=date.replace(hour=hour, minute=0, second=0, microsecond=0),
                duration_seconds=5,  # ~5 сек на озвучку времени
                metadata={
                    "hour": hour,
                    "minute": 0,
                    "text": self.TIME_SIGNAL_TEMPLATE.format(hour=hour, minute=0),
                }
            ))

            # === N:00-05 — Горячие новости (все категории) ===
            schedule.append(ScheduleEvent(
                event_type=SegmentType.NEWS_BLOCK,
                scheduled_time=date.replace(hour=hour, minute=0, second=5, microsecond=0),
                duration_seconds=180,  # 3 минуты на сводку
                metadata={
                    "hour": hour,
                    "type": "hot_news",
                    "categories": "all",
                }
            ))

            # === N:05-08 — Рекламный блок (самореклама) ===
            schedule.append(ScheduleEvent(
                event_type=SegmentType.AD_BLOCK,
                scheduled_time=date.replace(hour=hour, minute=5, second=0, microsecond=0),
                duration_seconds=30,
                metadata={
                    "script": self._get_ad_script(hour),
                }
            ))

            # === N:08-30 — Музыкальная программа (текущий стиль) ===
            preset = self._get_preset_for_hour(hour)
            schedule.append(ScheduleEvent(
                event_type=SegmentType.MUSIC_PROGRAM,
                scheduled_time=date.replace(hour=hour, minute=8, second=0, microsecond=0),
                duration_seconds=1320,  # 22 минуты до :30
                metadata={
                    "preset": preset,
                    "style": "main",
                }
            ))

            # === N:30 — Рекламный блок ===
            schedule.append(ScheduleEvent(
                event_type=SegmentType.AD_BLOCK,
                scheduled_time=date.replace(hour=hour, minute=30, second=0, microsecond=0),
                duration_seconds=30,
                metadata={
                    "script": self._get_ad_script(hour, is_half_hour=True),
                }
            ))

            # === N:30-58 — Музыка в СЛЕДУЮЩЕМ стиле (переход) ===
            next_hour = (hour + 1) % 24
            next_preset = self._get_preset_for_hour(next_hour)
            schedule.append(ScheduleEvent(
                event_type=SegmentType.MUSIC_PROGRAM,
                scheduled_time=date.replace(hour=hour, minute=30, second=30, microsecond=0),
                duration_seconds=1650,  # 27.5 минут до следующего часа
                metadata={
                    "preset": next_preset,
                    "style": "transition",  # Уже следующий стиль
                    "is_transition": True,
                }
            ))

        self.current_schedule = schedule
        logger.info(f"Generated daily schedule: {len(schedule)} events")
        return schedule

    def _get_preset_for_hour(self, hour: int) -> str:
        for (start, end), preset_name in TIME_PRESET_MAP.items():
            if start <= hour < end:
                return preset_name
        return "night"

    def _get_ad_script(self, hour: int, is_half_hour: bool = False) -> str:
        """Выбирает скрипт рекламы в зависимости от времени"""
        import random
        base = random.choice(self.AD_SCRIPTS)
        if is_half_hour:
            return f"Половина {hour}го. {base}"
        return base


class RadioAutomation:
    """Главный класс автоматизации: генерирует, микширует, стримит"""

    def __init__(
        self,
        music_dir: str = "C:/Users/tomas/ai-radio/music_output",
        news_dir: str = "C:/Users/tomas/ai-radio/newsfeed",
        output_dir: str = "C:/Users/tomas/ai-radio/radio_output",
        tts_script: str = "C:/Users/tomas/voicebox_tts.py",
        sample_rate: int = 32000,
    ):
        self.music_dir = Path(music_dir)
        self.news_dir = Path(news_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.tts_script = tts_script
        self.sample_rate = sample_rate

        # Компоненты
        self.music_gen = MusicGenDirectML(output_dir=str(self.music_dir))
        self.stitcher = AudioStitcher(sample_rate=sample_rate, output_dir=str(self.output_dir / "stitched"))
        self.scheduler = ProgramScheduler()

        # Ducking
        self.duck_level = 0.15
        self.duck_fade_ms = 100

        # Кэш сгенерированных сегментов
        self.segment_cache: Dict[str, Path] = {}

    def generate_tts(self, text: str, output_name: str) -> Path:
        """Генерирует TTS — сначала Voicebox, fallback на Edge TTS"""
        output_path = self.output_dir / "tts_cache" / output_name
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_path.exists():
            return output_path

        # Сначала пробуем Voicebox (если сервер жив)
        try:
            # Создаём временный файл с текстом
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as tf:
                tf.write(text)
                temp_text_path = tf.name

            try:
                cmd = [
                    "C:/Users/tomas/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe",
                    self.tts_script,
                    temp_text_path,
                    str(output_path),
                ]
                logger.info(f"TTS (Voicebox): {text[:60]}...")
                result = subprocess.run(cmd, capture_output=True, timeout=30)
                if result.returncode == 0 and output_path.exists():
                    logger.info(f"Voicebox TTS OK")
                    return output_path
                else:
                    logger.warning(f"Voicebox failed: {result.stderr.decode()[:200]}")
            finally:
                try:
                    os.unlink(temp_text_path)
                except:
                    pass
        except Exception as e:
            logger.warning(f"Voicebox exception: {e}")

        # Fallback: Edge TTS (Dmitry voice - работает)
        try:
            logger.info(f"TTS (Edge fallback): {text[:60]}...")
            import asyncio
            import edge_tts

            async def _edge_tts():
                communicate = edge_tts.Communicate(text, "ru-RU-DmitryNeural")
                await communicate.save(str(output_path))

            asyncio.run(_edge_tts())
            if output_path.exists():
                logger.info(f"Edge TTS OK")
                return output_path
        except Exception as e:
            logger.error(f"Edge TTS failed: {e}")

        raise RuntimeError("All TTS methods failed")

    def generate_time_signal(self, hour: int, minute: int) -> Path:
        """Генерирует сигнал точного времени"""
        text = f"Radio ArmsgeddonFM. {hour} часов {minute:02d} минут. Точное время."
        return self.generate_tts(text, f"time_signal_{hour:02d}_{minute:02d}.wav")

    def generate_ad_block(self, script: str) -> Path:
        """Генерирует рекламный блок"""
        return self.generate_tts(script, f"ad_{hash(script) % 10000:04d}.wav")

    def load_news_for_hour(self, hour: int) -> List[Dict]:
        """Загружает горячие новости из newsfeed за последний час"""
        news_items = []
        # Ищем во всех 17 категориях
        for cat_dir in self.news_dir.iterdir():
            if not cat_dir.is_dir():
                continue
            for news_file in cat_dir.glob("*.txt"):
                try:
                    # Проверяем время файла (модификация за последний час)
                    mtime = datetime.fromtimestamp(news_file.stat().st_mtime)
                    if (datetime.now() - mtime).total_seconds() < 3600:
                        text = news_file.read_text(encoding='utf-8').strip()
                        if text:
                            news_items.append({
                                "category": cat_dir.name,
                                "text": text[:300],  # Ограничиваем длину
                                "source_file": str(news_file),
                            })
                except Exception as e:
                    logger.warning(f"Failed to read {news_file}: {e}")

        # Сортируем по важности (можно добавить scoring)
        news_items = news_items[:10]  # Топ-10 новостей
        logger.info(f"Loaded {len(news_items)} hot news items for hour {hour}")
        return news_items

    def compile_news_block(self, hour: int) -> Path:
        """Компилирует блок новостей: вводная + 5-7 новостей + заставка"""
        news = self.load_news_for_hour(hour)

        # Формируем текст для TTS
        parts = [
            f"Горячие новости на {hour:02d} часов. Главное за последнее время.",
        ]
        for i, item in enumerate(news[:7], 1):
            parts.append(f"Новость номер {i}. {item['text']}.")
        parts.append("Подробности в нашем телеграм канале Radio ArmsgeddonFM.")

        full_text = " ".join(parts)
        return self.generate_tts(full_text, f"news_block_{hour:02d}_{datetime.now().strftime('%H%M')}.wav")

    def ensure_music_for_preset(self, preset: str, minutes: int) -> Path:
        """Гарантирует наличие музыкальных сегментов для пресета"""
        preset_dir = self.music_dir / preset
        preset_dir.mkdir(parents=True, exist_ok=True)

        existing = list(preset_dir.glob("*.wav"))
        total_sec = 0
        for f in existing:
            try:
                info = torchaudio.info(str(f))
                total_sec += info.num_frames / info.sample_rate
            except:
                pass

        need_sec = minutes * 60
        if total_sec >= need_sec:
            return preset_dir

        # Генерируем недостающее
        need_min = int((need_sec - total_sec) / 60) + 1
        segs = (need_min * 60) // 30 + 2
        logger.info(f"Generating {segs} segments for {preset} ({need_min} min)")

        paths = self.music_gen.generate_batch(count=segs, preset_name=preset)
        for p in paths:
            p.rename(preset_dir / p.name)

        return preset_dir

    def build_hourly_music(self, preset: str, duration_min: int, style: str = "main") -> Path:
        """Собирает часовой музыкальный блок с кроссфейдом"""
        self.ensure_music_for_preset(preset, duration_min + 5)

        output_name = f"music_{preset}_{style}_{duration_min}min_{datetime.now().strftime('%Y%m%d_%H%M')}.wav"
        return self.stitcher.create_hourly_track(
            str(self.music_dir / preset),
            preset,
            target_duration_minutes=duration_min,
            output_name=output_name,
        )

    def mix_segment(self, music_path: Path, speech_path: Path, start_sec: float) -> Tuple[Path, torch.Tensor]:
        """Накладывает речь на музыку с дакингом, возвращает (путь, смешанный тензор)"""
        music = self.load_audio(music_path)
        speech = self.load_audio(speech_path)

        start_sample = int(start_sec * self.sample_rate)
        music = self.duck_and_overlay(music, speech, start_sample)

        output_path = self.output_dir / f"mixed_{music_path.stem}_{speech_path.stem}.wav"
        torchaudio.save(str(output_path), music, self.sample_rate)
        return output_path, music

    def load_audio(self, path: Path) -> torch.Tensor:
        wav, sr = torchaudio.load(str(path))
        if sr != self.sample_rate:
            wav = torchaudio.transforms.Resample(sr, self.sample_rate)(wav)
        if wav.shape[0] > 1:
            wav = wav.mean(dim=0, keepdim=True)
        return wav

    def duck_and_overlay(self, music: torch.Tensor, speech: torch.Tensor, start_sample: int) -> torch.Tensor:
        """Дакинг + наложение"""
        music = music.clone()
        fade_samples = int(self.duck_fade_ms * self.sample_rate / 1000)
        speech_len = speech.shape[-1]
        end_sample = start_sample + speech_len

        start_sample = max(0, min(start_sample, music.shape[-1] - 1))
        end_sample = max(start_sample, min(end_sample, music.shape[-1]))

        duck_len = end_sample - start_sample
        if duck_len <= 0:
            return music

        envelope = torch.ones(duck_len)
        fade_in = min(fade_samples, duck_len // 2)
        fade_out = min(fade_samples, duck_len // 2)

        if fade_in > 0:
            envelope[:fade_in] = torch.linspace(1.0, self.duck_level, fade_in)
        if fade_out > 0:
            envelope[-fade_out:] = torch.linspace(self.duck_level, 1.0, fade_out)
        if duck_len > fade_in + fade_out:
            envelope[fade_in:-fade_out] = self.duck_level

        music[0, start_sample:end_sample] *= envelope
        music[0, start_sample:end_sample] += speech[0]

        # Нормализация
        max_val = music.abs().max()
        if max_val > 0.95:
            music = music * (0.95 / max_val)

        return music

    def build_program_block(self, event: ScheduleEvent) -> Path:
        """Строит аудио-блок для события расписания"""
        logger.info(f"Building block: {event.event_type.value} at {event.scheduled_time}")

        if event.event_type == SegmentType.TIME_SIGNAL:
            return self.generate_time_signal(event.metadata["hour"], event.metadata["minute"])

        elif event.event_type == SegmentType.NEWS_BLOCK:
            return self.compile_news_block(event.metadata["hour"])

        elif event.event_type == SegmentType.AD_BLOCK:
            return self.generate_ad_block(event.metadata["script"])

        elif event.event_type == SegmentType.MUSIC_PROGRAM:
            preset = event.metadata["preset"]
            style = event.metadata.get("style", "main")
            duration = int(event.duration_seconds / 60)
            return self.build_hourly_music(preset, duration, style)

        else:
            raise ValueError(f"Unknown event type: {event.event_type}")

    def assemble_hour(self, hour: int, date: datetime) -> Path:
        """Собирает полный часовой эфир из блоков по расписанию"""
        schedule = self.scheduler.generate_daily_schedule(date)
        hour_events = [e for e in schedule if e.scheduled_time.hour == hour]

        logger.info(f"=== Assembling hour {hour:02d} ({len(hour_events)} blocks) ===")

        # Строим каждый блок
        blocks = []
        for event in hour_events:
            block_path = self.build_program_block(event)
            blocks.append((block_path, event))

        # Сшиваем в итоговый часовой файл
        final_path = self.output_dir / f"broadcast_{date.strftime('%Y%m%d')}_{hour:02d}00.wav"

        # Просто конкатенируем (блоки уже с правильными паузами)
        full_audio = torch.zeros(1, 0)
        for block_path, event in blocks:
            audio = self.load_audio(block_path)
            full_audio = torch.cat([full_audio, audio], dim=-1)
            logger.info(f"  Added {event.event_type.value}: {audio.shape[-1]/self.sample_rate:.1f}s")

        torchaudio.save(str(final_path), full_audio, self.sample_rate)
        duration = full_audio.shape[-1] / self.sample_rate / 60
        logger.info(f"✅ Hour {hour:02d} assembled: {final_path} ({duration:.1f} min)")

        return final_path

    def run_broadcast_day(self, date: Optional[datetime] = None):
        """Запускает сборку эфира на сутки"""
        if date is None:
            date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        logger.info(f"🎙️ Building broadcast day: {date.strftime('%Y-%m-%d')}")

        for hour in range(24):
            try:
                self.assemble_hour(hour, date)
            except Exception as e:
                logger.error(f"Failed to assemble hour {hour}: {e}", exc_info=True)

        logger.info("✅ Full broadcast day assembled")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Radio ArmsgeddonFM Automation")
    parser.add_argument("--hour", type=int, help="Build specific hour (0-23)")
    parser.add_argument("--day", action="store_true", help="Build full day")
    parser.add_argument("--date", type=str, help="Date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    automation = RadioAutomation()

    if args.date:
        base_date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if args.day:
        automation.run_broadcast_day(base_date)
    elif args.hour is not None:
        automation.assemble_hour(args.hour, base_date)
    else:
        # По умолчанию — текущий час
        automation.assemble_hour(datetime.now().hour, base_date)


if __name__ == "__main__":
    main()