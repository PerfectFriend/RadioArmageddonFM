#!/usr/bin/env python3
"""
MusicGen DirectML Client for Radio ArmsgeddonFM
Local music generation on AMD 780M via DirectML/CPU
"""

import os
import sys
import torch
import torchaudio
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Radio presets by time of day
RADIO_PRESETS = {
    "morning": {
        "prompt": "upbeat electronic music, 110 bpm, energetic, synthesizers, optimistic, morning vibes, melodic",
        "duration": 30,
        "temperature": 1.0,
        "top_k": 250,
        "top_p": 0.9,
    },
    "day": {
        "prompt": "chill lo-fi hip hop, 85 bpm, relaxed, jazz samples, background music, steady groove, nostalgic",
        "duration": 30,
        "temperature": 1.0,
        "top_k": 250,
        "top_p": 0.9,
    },
    "evening": {
        "prompt": "synthwave, 100 bpm, nostalgic, retro, atmospheric, driving bass, cinematic, sunset vibes",
        "duration": 30,
        "temperature": 1.0,
        "top_k": 250,
        "top_p": 0.9,
    },
    "night": {
        "prompt": "dark ambient, 60 bpm, minimal, drone, deep bass, meditative, slow evolving, night atmosphere",
        "duration": 30,
        "temperature": 0.8,
        "top_k": 200,
        "top_p": 0.85,
    },
    "late_night": {
        "prompt": "drone ambient, 50 bpm, very slow, sub-bass, hypnotic, minimal, deep space, trance inducing",
        "duration": 30,
        "temperature": 0.7,
        "top_k": 150,
        "top_p": 0.8,
    },
}

# Time-based preset mapping
TIME_PRESET_MAP = {
    (6, 10): "morning",
    (10, 17): "day",
    (17, 21): "evening",
    (21, 24): "night",
    (0, 6): "late_night",
}


class MusicGenDirectML:
    def __init__(
        self,
        model_path: str = "C:/Users/tomas/ai-radio/models/musicgen-small",
        use_directml: bool = True,
        output_dir: str = "C:/Users/tomas/ai-radio/music_output",
    ):
        self.model_path = Path(model_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Device selection - FORCE CPU for MusicGen (DirectML has operator gaps)
        self.device = torch.device("cpu")
        logger.info("Using CPU device for MusicGen (DirectML has operator gaps)")

        # Load model
        self.model = None
        self._load_model()

    def _load_model(self):
        """Load MusicGen model from local path"""
        try:
            from audiocraft.models import MusicGen
            logger.info(f"Loading MusicGen from {self.model_path}...")

            # Load on target device (DirectML or CPU)
            self.model = MusicGen.get_pretrained(str(self.model_path), device=self.device)
            logger.info(f"MusicGen loaded! Sample rate: {self.model.sample_rate}")

        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

    def get_current_preset(self) -> Dict[str, Any]:
        """Get preset based on current time"""
        hour = datetime.now().hour
        for (start, end), preset_name in TIME_PRESET_MAP.items():
            if start <= hour < end:
                preset = RADIO_PRESETS[preset_name].copy()
                preset["preset_name"] = preset_name
                return preset
        # Fallback
        preset = RADIO_PRESETS["night"].copy()
        preset["preset_name"] = "night"
        return preset

    def generate(
        self,
        prompt: Optional[str] = None,
        duration: int = 30,
        temperature: float = 1.0,
        top_k: int = 250,
        top_p: float = 0.9,
        progress: bool = True,
    ) -> torch.Tensor:
        """
        Generate music with MusicGen
        Returns: waveform tensor [1, 1, samples]
        """
        if prompt is None:
            preset = self.get_current_preset()
            prompt = preset["prompt"]
            duration = preset["duration"]
            temperature = preset["temperature"]
            top_k = preset["top_k"]
            top_p = preset["top_p"]

        logger.info(f"Generating: {prompt[:80]}...")

        # Generate
        with torch.no_grad():
            wav = self.model.generate(
                [prompt],
                progress=progress,
            )

        # Trim to exact duration
        target_samples = duration * self.model.sample_rate
        if wav.shape[-1] > target_samples:
            wav = wav[..., :target_samples]

        logger.info(f"Generated shape: {wav.shape} ({wav.shape[-1]/self.model.sample_rate:.1f}s)")
        return wav

    def generate_and_save(
        self,
        filename: Optional[str] = None,
        **kwargs
    ) -> Path:
        """Generate and save to file"""
        wav = self.generate(**kwargs)

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            preset = kwargs.get("prompt", "custom")[:30].replace(" ", "_")
            filename = f"musicgen_{preset}_{timestamp}.wav"

        output_path = self.output_dir / filename
        torchaudio.save(str(output_path), wav[0].cpu(), self.model.sample_rate)
        logger.info(f"Saved: {output_path}")
        return output_path

    def generate_batch(
        self,
        count: int,
        preset_name: Optional[str] = None,
        **kwargs
    ) -> List[Path]:
        """Generate multiple tracks"""
        paths = []
        for i in range(count):
            if preset_name and preset_name in RADIO_PRESETS:
                preset = RADIO_PRESETS[preset_name].copy()
                preset["preset_name"] = preset_name
                kwargs.update({
                    "prompt": preset["prompt"],
                    "duration": preset["duration"],
                    "temperature": preset["temperature"],
                    "top_k": preset["top_k"],
                    "top_p": preset["top_p"],
                })
            filename = f"batch_{preset_name or 'custom'}_{i+1:03d}_{datetime.now().strftime('%H%M%S')}.wav"
            path = self.generate_and_save(filename=filename, **kwargs)
            paths.append(path)
        return paths


def main():
    import argparse
    parser = argparse.ArgumentParser(description="MusicGen DirectML CLI")
    parser.add_argument("--prompt", type=str, help="Custom prompt")
    parser.add_argument("--preset", choices=list(RADIO_PRESETS.keys()), help="Use radio preset")
    parser.add_argument("--duration", type=int, default=30, help="Duration in seconds")
    parser.add_argument("--count", type=int, default=1, help="Number of tracks")
    parser.add_argument("--output-dir", type=str, default="C:/Users/tomas/ai-radio/music_output")
    parser.add_argument("--cpu", action="store_true", help="Force CPU mode")
    args = parser.parse_args()

    client = MusicGenDirectML(
        use_directml=not args.cpu,
        output_dir=args.output_dir,
    )

    if args.count > 1:
        paths = client.generate_batch(args.count, preset_name=args.preset)
        print(f"Generated {len(paths)} tracks:")
        for p in paths:
            print(f"  {p}")
    else:
        path = client.generate_and_save(
            prompt=args.prompt,
            duration=args.duration,
        )
        print(f"Generated: {path}")


if __name__ == "__main__":
    main()