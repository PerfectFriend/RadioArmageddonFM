#!/usr/bin/env python3
"""
Riffusion DirectML Client for Radio ArmsgeddonFM
Lightweight local music generation via spectrogram diffusion.
Works on CPU/DirectML, fast (~5-10 sec per track), no heavy deps.
"""

import os
import time
import torch
import torchaudio
from pathlib import Path
from typing import Optional, List
import numpy as np

# Try DirectML
try:
    import torch_directml
    HAS_DIRECTML = True
except ImportError:
    HAS_DIRECTML = False


class RiffusionGenerator:
    """Riffusion music generator via HuggingFace diffusers."""
    
    def __init__(self, device: str = "auto", model_id: str = "riffusion/riffusion-model-v1"):
        """
        Initialize Riffusion generator.
        
        Args:
            device: "auto", "cuda", "directml", "cpu"
            model_id: HuggingFace model ID
        """
        self.model_id = model_id
        self.device = self._select_device(device)
        self.pipe = None
        
    def _select_device(self, device: str) -> torch.device:
        if device == "auto":
            if torch.cuda.is_available():
                return torch.device("cuda")
            elif HAS_DIRECTML:
                import torch_directml
                return torch_directml.device()
            else:
                return torch.device("cpu")
        elif device == "directml" and HAS_DIRECTML:
            import torch_directml
            return torch_directml.device()
        elif device == "cuda" and torch.cuda.is_available():
            return torch.device("cuda")
        else:
            return torch.device("cpu")
    
    def load(self):
        """Load the Riffusion pipeline."""
        from diffusers import StableDiffusionPipeline
        from diffusers.schedulers import DDIMScheduler
        
        print(f"Loading Riffusion on {self.device}...")
        
        self.pipe = StableDiffusionPipeline.from_pretrained(
            self.model_id,
            torch_dtype=torch.float16 if self.device.type != "cpu" else torch.float32,
            safety_checker=None,
            requires_safety_checker=False,
        )
        self.pipe = self.pipe.to(self.device)
        
        # Use DDIM scheduler for faster generation
        self.pipe.scheduler = DDIMScheduler.from_config(self.pipe.scheduler.config)
        
        # Enable memory efficient attention if available
        try:
            self.pipe.enable_xformers_memory_efficient_attention()
        except:
            pass
        
        print(f"Riffusion loaded on {self.device}")
    
    def generate_spectrogram(self, prompt: str, negative_prompt: str = "", 
                            width: int = 512, height: int = 512,
                            num_inference_steps: int = 50, guidance_scale: float = 7.5,
                            seed: Optional[int] = None) -> np.ndarray:
        """Generate spectrogram image from text prompt."""
        if self.pipe is None:
            self.load()
        
        generator = torch.Generator(device=self.device)
        if seed is not None:
            generator.manual_seed(seed)
        
        with torch.autocast(device_type=self.device.type if self.device.type != "cpu" else "cpu"):
            image = self.pipe(
                prompt=prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                generator=generator,
            ).images[0]
        
        return np.array(image)
    
    def spectrogram_to_audio(self, spectrogram: np.ndarray, sample_rate: int = 44100,
                            n_fft: int = 1024, hop_length: int = 256,
                            n_iter: int = 32) -> np.ndarray:
        """Convert spectrogram image to audio using Griffin-Lim."""
        import librosa
        
        # Riffusion spectrogram params
        vmin = -100  # dB
        vmax = 0     # dB
        
        # Convert image to magnitude spectrogram
        spec_db = (spectrogram.astype(np.float32) / 255.0) * (vmax - vmin) + vmin
        spec = librosa.db_to_power(spec_db)
        
        # Griffin-Lim phase reconstruction
        audio = librosa.griffinlim(
            spec,
            n_iter=n_iter,
            hop_length=hop_length,
            n_fft=n_fft,
        )
        
        return audio.astype(np.float32)
    
    def generate(self, prompt: str, duration: float = 10.0, 
                sample_rate: int = 44100, seed: Optional[int] = None) -> np.ndarray:
        """
        Generate audio from text prompt.
        
        Args:
            prompt: Text description of music
            duration: Target duration in seconds
            sample_rate: Output sample rate
            seed: Random seed for reproducibility
            
        Returns:
            Audio array (float32, -1 to 1)
        """
        # Calculate spectrogram dimensions for target duration
        hop_length = 256
        n_fft = 1024
        frames = int(duration * sample_rate / hop_length)
        
        # Riffusion uses 512x512 latent, we need ~frames width
        # Generate wider spectrogram and crop
        width = max(512, frames + 512)
        height = 512
        
        # Enhanced prompt for better quality
        enhanced_prompt = f"{prompt}, high quality, professional production, {duration}s"
        negative = "low quality, distorted, noisy, muffled, silent, static"
        
        print(f"Generating spectrogram for: {prompt}")
        spec = self.generate_spectrogram(
            enhanced_prompt, 
            negative_prompt=negative,
            width=width,
            height=height,
            num_inference_steps=30,
            seed=seed,
        )
        
        print("Converting to audio...")
        audio = self.spectrogram_to_audio(spec, sample_rate=sample_rate)
        
        # Trim/pad to target duration
        target_samples = int(duration * sample_rate)
        if len(audio) > target_samples:
            audio = audio[:target_samples]
        elif len(audio) < target_samples:
            audio = np.pad(audio, (0, target_samples - len(audio)))
        
        # Normalize
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio = audio / max_val * 0.95
        
        return audio
    
    def save_audio(self, audio: np.ndarray, path: str, sample_rate: int = 44100):
        """Save audio to WAV file."""
        torchaudio.save(
            path,
            torch.from_numpy(audio).unsqueeze(0),
            sample_rate,
            encoding="PCM_S",
            bits_per_sample=16,
        )


# Radio presets
RADIO_PRESETS = {
    "morning": "upbeat electronic, 110 bpm, energetic, synthesizers, optimistic, melodic",
    "day": "chill lo-fi hip hop, 85 bpm, relaxed, jazz samples, background, smooth",
    "evening": "synthwave, 100 bpm, nostalgic, retro, atmospheric, analog synthesizers",
    "night": "dark ambient, 60 bpm, minimal, drone, deep bass, meditative, slow",
    "late_night": "drone ambient, 50 bpm, very slow, sub-bass, hypnotic, ethereal",
    "energy": "high energy electronic, 128 bpm, driving, powerful, festival",
    "focus": "ambient electronic, 70 bpm, minimal, repetitive, concentration, flow",
}

def generate_radio_block(generator: RiffusionGenerator, preset: str, 
                        duration: int = 1800, output_dir: str = "output/music"):
    """Generate a radio music block (default 30 min)."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    prompt = RADIO_PRESETS.get(preset, preset)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{preset}_{timestamp}.wav"
    filepath = Path(output_dir) / filename
    
    print(f"\n=== Generating {preset} block ({duration}s) ===")
    print(f"Prompt: {prompt}")
    
    # Generate in chunks (Riffusion max ~30s per generation)
    chunk_duration = 30
    chunks = []
    
    for i in range(0, duration, chunk_duration):
        chunk_dur = min(chunk_duration, duration - i)
        seed = int(time.time() * 1000) + i if i > 0 else None
        
        chunk = generator.generate(prompt, duration=chunk_dur, seed=seed)
        chunks.append(chunk)
        
        # Crossfade between chunks
        if len(chunks) > 1:
            fade_len = int(0.5 * 44100)  # 0.5s crossfade
            chunks[-2][-fade_len:] *= np.linspace(1, 0, fade_len)
            chunks[-1][:fade_len] *= np.linspace(0, 1, fade_len)
    
    full_audio = np.concatenate(chunks)
    
    generator.save_audio(full_audio, str(filepath))
    print(f"Saved: {filepath}")
    
    return str(filepath)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Riffusion Radio Music Generator")
    parser.add_argument("--preset", choices=list(RADIO_PRESETS.keys()), default="day")
    parser.add_argument("--duration", type=int, default=1800)
    parser.add_argument("--output", default="output/music")
    parser.add_argument("--device", choices=["auto", "cpu", "directml", "cuda"], default="auto")
    args = parser.parse_args()
    
    gen = RiffusionGenerator(device=args.device)
    generate_radio_block(gen, args.preset, args.duration, args.output)