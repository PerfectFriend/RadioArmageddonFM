#!/usr/bin/env python3
"""
Autonomous Evolution Runner for Radio ArmsgeddonFM
Runs 20 evolution cycles with tests, debugging, and USB backups
"""

import os
import sys
import json
import time
import shutil
import subprocess
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import threading

# Add project root to path
sys.path.insert(0, "C:/Users/tomas/ai-radio")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("C:/Users/tomas/ai-radio/evolution.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class EvolutionRunner:
    def __init__(
        self,
        project_root: str = "C:/Users/tomas/ai-radio",
        usb_backup_path: str = "D:/backups/radio_armsgeddonfm",
        cycles: int = 20,
        interval_hours: int = 2,
    ):
        self.project_root = Path(project_root)
        self.usb_backup_path = Path(usb_backup_path)
        self.cycles = cycles
        self.interval_hours = interval_hours
        self.cycle = 0
        self.results = []

        # Ensure backup directory exists
        self.usb_backup_path.mkdir(parents=True, exist_ok=True)

        # Version badge counter
        self.version = self._load_version()

    def _load_version(self) -> int:
        """Load current version from badge file"""
        badge_file = self.project_root / "version_badge.txt"
        if badge_file.exists():
            try:
                return int(badge_file.read_text().strip())
            except:
                pass
        return 0

    def _save_version(self):
        """Save version badge"""
        badge_file = self.project_root / "version_badge.txt"
        badge_file.write_text(str(self.version))

    def _get_badge(self) -> str:
        """Get version badge string like A00, A01, A02..."""
        return f"A{self.version:02d}"

    def run_tests(self) -> Dict[str, Any]:
        """Run test suite"""
        logger.info("🧪 Running tests...")
        results = {
            "passed": 0,
            "failed": 0,
            "errors": [],
        }

        # Test 1: MusicGen import and load
        try:
            from musicgen_directml import MusicGenDirectML
            mg = MusicGenDirectML(use_directml=False)  # CPU for test
            results["passed"] += 1
            logger.info("  ✅ MusicGen import & load")
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"MusicGen: {e}")
            logger.error(f"  ❌ MusicGen: {e}")

        # Test 2: AudioStitcher
        try:
            from audio_stitcher import AudioStitcher
            stitcher = AudioStitcher()
            results["passed"] += 1
            logger.info("  ✅ AudioStitcher import")
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"AudioStitcher: {e}")
            logger.error(f"  ❌ AudioStitcher: {e}")

        # Test 3: DJPipeline import
        try:
            from dj_pipeline import DJPipeline
            results["passed"] += 1
            logger.info("  ✅ DJPipeline import")
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"DJPipeline: {e}")
            logger.error(f"  ❌ DJPipeline: {e}")

        # Test 4: Music generation (quick 5-second test)
        try:
            from musicgen_directml import MusicGenDirectML
            mg = MusicGenDirectML(use_directml=False)
            wav = mg.generate(prompt="test beat", duration=5, progress=False)
            assert wav.shape[-1] > 0
            results["passed"] += 1
            logger.info("  ✅ Music generation (5s test)")
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"Generation: {e}")
            logger.error(f"  ❌ Generation: {e}")

        # Test 5: File structure
        required_dirs = [
            "music_output",
            "newsfeed",
            "radio_output",
            "models/musicgen-small",
        ]
        for d in required_dirs:
            if (self.project_root / d).exists():
                results["passed"] += 1
                logger.info(f"  ✅ Dir exists: {d}")
            else:
                results["failed"] += 1
                results["errors"].append(f"Missing dir: {d}")
                logger.error(f"  ❌ Missing dir: {d}")

        logger.info(f"Tests: {results['passed']} passed, {results['failed']} failed")
        return results

    def run_debug_checks(self) -> Dict[str, Any]:
        """Run debugging checks"""
        logger.info("🔍 Running debug checks...")
        results = {
            "checks": [],
            "warnings": [],
            "errors": [],
        }

        # Check 1: Disk space
        try:
            import psutil
            disk = psutil.disk_usage(str(self.project_root))
            free_gb = disk.free / (1024**3)
            if free_gb < 5:
                results["warnings"].append(f"Low disk space: {free_gb:.1f}GB free")
            results["checks"].append(f"Disk: {free_gb:.1f}GB free")
        except:
            results["checks"].append("Disk: unknown")

        # Check 2: GPU/DRAM availability
        try:
            import torch
            import torch_directml
            if torch_directml.is_available():
                results["checks"].append("DirectML: Available")
            else:
                results["warnings"].append("DirectML: Not available, using CPU")
        except:
            results["errors"].append("DirectML check failed")

        # Check 3: Model files
        model_files = [
            "models/musicgen-small/config.json",
            "models/musicgen-small/model.safetensors",
            "models/musicgen-small/state_dict.bin",
            "models/musicgen-small/compression_state_dict.bin",
        ]
        for f in model_files:
            path = self.project_root / f
            if path.exists():
                size_mb = path.stat().st_size / (1024**2)
                results["checks"].append(f"Model file: {f} ({size_mb:.1f}MB)")
            else:
                results["errors"].append(f"Missing model file: {f}")

        # Check 4: Python environment
        try:
            import torch
            import torchaudio
            import audiocraft
            results["checks"].append(f"PyTorch: {torch.__version__}")
            results["checks"].append(f"TorchAudio: {torchaudio.__version__}")
            results["checks"].append("AudioCraft: OK")
        except Exception as e:
            results["errors"].append(f"Environment: {e}")

        # Check 5: USB backup drive
        if self.usb_backup_path.exists():
            try:
                import psutil
                disk = psutil.disk_usage(str(self.usb_backup_path))
                free_gb = disk.free / (1024**3)
                results["checks"].append(f"USB Backup: {free_gb:.1f}GB free")
                if free_gb < 2:
                    results["warnings"].append(f"USB backup low space: {free_gb:.1f}GB")
            except:
                results["checks"].append("USB Backup: Connected")
        else:
            results["warnings"].append("USB backup drive not mounted")

        logger.info(f"Debug: {len(results['checks'])} checks, {len(results['warnings'])} warnings, {len(results['errors'])} errors")
        return results

    def create_backup(self, cycle: int, badge: str) -> Path:
        """Create backup to USB drive"""
        logger.info(f"💾 Creating backup for cycle {cycle} ({badge})...")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"radio_{badge}_cycle{cycle:02d}_{timestamp}"
        backup_dir = self.usb_backup_path / backup_name
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Files/dirs to backup
        backup_items = [
            "musicgen_directml.py",
            "audio_stitcher.py",
            "dj_pipeline.py",
            "musicgen_directml.py",
            "news_scraper_production.py",
            "top100_feeds.py",
            "models/musicgen-small",
            "music_output",
            "newsfeed",
            "radio_output",
            "version_badge.txt",
            "evolution.log",
            "ChainZap_Evolution_Report.md",
        ]

        copied = 0
        for item in backup_items:
            src = self.project_root / item
            if src.exists():
                dst = backup_dir / item
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                copied += 1

        # Create manifest
        manifest = {
            "cycle": cycle,
            "badge": badge,
            "timestamp": timestamp,
            "items_copied": copied,
            "source": str(self.project_root),
        }
        (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

        logger.info(f"  Backup created: {backup_dir} ({copied} items)")
        return backup_dir

    def run_evolution_cycle(self) -> Dict[str, Any]:
        """Run one evolution cycle"""
        self.cycle += 1
        self.version += 1
        badge = self._get_badge()
        self._save_version()

        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 EVOLUTION CYCLE {self.cycle}/{self.cycles} - VERSION {badge}")
        logger.info(f"{'='*60}")

        cycle_start = time.time()
        result = {
            "cycle": self.cycle,
            "badge": badge,
            "timestamp": datetime.now().isoformat(),
            "tests": None,
            "debug": None,
            "generation": None,
            "backup": None,
            "duration_seconds": 0,
            "success": False,
        }

        try:
            # Phase 1: Tests
            logger.info("Phase 1: Running tests...")
            result["tests"] = self.run_tests()

            # Phase 2: Debug checks
            logger.info("Phase 2: Debug checks...")
            result["debug"] = self.run_debug_checks()

            # Phase 3: Generate music for current preset
            logger.info("Phase 3: Music generation...")
            from musicgen_directml import MusicGenDirectML
            mg = MusicGenDirectML(use_directml=False)
            preset = mg.get_current_preset()
            preset_name = preset["preset_name"]
            path = mg.generate_and_save()
            result["generation"] = {
                "preset": preset_name,
                "file": str(path),
                "size_mb": path.stat().st_size / (1024**2),
            }
            logger.info(f"  Generated: {path.name} ({result['generation']['size_mb']:.1f}MB)")

            # Phase 4: Create backup
            logger.info("Phase 4: USB backup...")
            backup_dir = self.create_backup(self.cycle, badge)
            result["backup"] = str(backup_dir)

            result["success"] = True
            logger.info(f"✅ Cycle {self.cycle} COMPLETE - {badge}")

        except Exception as e:
            logger.error(f"❌ Cycle {self.cycle} FAILED: {e}", exc_info=True)
            result["error"] = str(e)
            result["success"] = False

        result["duration_seconds"] = time.time() - cycle_start
        self.results.append(result)

        # Save cycle result
        result_file = self.project_root / f"evolution_cycle_{self.cycle:02d}_{badge}.json"
        result_file.write_text(json.dumps(result, indent=2))

        return result

    def run_all_cycles(self):
        """Run all evolution cycles"""
        logger.info(f"🚀 Starting autonomous evolution: {self.cycles} cycles, every {self.interval_hours}h")

        for i in range(self.cycles):
            if i > 0:
                # Wait between cycles
                wait_seconds = self.interval_hours * 3600
                logger.info(f"⏳ Waiting {self.interval_hours}h until next cycle...")
                time.sleep(wait_seconds)

            self.run_evolution_cycle()

        # Final summary
        self._generate_final_report()

    def _generate_final_report(self):
        """Generate final evolution report"""
        logger.info("\n" + "="*60)
        logger.info("📊 EVOLUTION COMPLETE - FINAL REPORT")
        logger.info("="*60)

        successful = sum(1 for r in self.results if r["success"])
        failed = len(self.results) - successful

        report = {
            "total_cycles": self.cycles,
            "successful": successful,
            "failed": failed,
            "final_badge": self._get_badge(),
            "cycles": self.results,
            "completed_at": datetime.now().isoformat(),
        }

        report_file = self.project_root / f"EVOLUTION_FINAL_REPORT_{self._get_badge()}.json"
        report_file.write_text(json.dumps(report, indent=2))

        logger.info(f"Total cycles: {self.cycles}")
        logger.info(f"Successful: {successful}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Final version: {self._get_badge()}")
        logger.info(f"Report saved: {report_file}")

        # Send Telegram summary
        self._send_telegram_summary(report)

    def _send_telegram_summary(self, report: Dict):
        """Send summary to Telegram"""
        try:
            msg = f"🎵 Radio ArmsgeddonFM - Evolution Complete\n"
            msg += f"Cycles: {report['total_cycles']}\n"
            msg += f"✅ Success: {report['successful']}\n"
            msg += f"❌ Failed: {report['failed']}\n"
            msg += f"🏷️ Final Badge: {report['final_badge']}\n"
            msg += f"⏰ Completed: {report['completed_at']}"

            subprocess.run([
                "C:/Users/tomas/AppData/Local/hermes/hermes-agent/venv/Scripts/hermes.exe",
                "send", "--to", "telegram:143293811", msg
            ], capture_output=True, timeout=30)
            logger.info("📱 Telegram summary sent")
        except Exception as e:
            logger.warning(f"Telegram failed: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Autonomous Evolution Runner")
    parser.add_argument("--cycles", type=int, default=20, help="Number of evolution cycles")
    parser.add_argument("--interval", type=int, default=2, help="Interval between cycles (hours)")
    parser.add_argument("--usb", type=str, default="D:/backups/radio_armsgeddonfm", help="USB backup path")
    parser.add_argument("--single", action="store_true", help="Run single cycle only")
    args = parser.parse_args()

    runner = EvolutionRunner(
        cycles=args.cycles,
        interval_hours=args.interval,
        usb_backup_path=args.usb,
    )

    if args.single:
        runner.run_evolution_cycle()
    else:
        runner.run_all_cycles()


if __name__ == "__main__":
    main()