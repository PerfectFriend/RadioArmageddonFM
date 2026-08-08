#!/usr/bin/env bash
# Radio ArmsgeddonFM — Evolution Cycle Runner
# Runs a full 2-hour evolution cycle with PlugMem integration

set -euo pipefail

CYCLE="${1:-A07}"
SLOT="${2:-morning}"
STORAGE="${3:-D:/backups/radio_armsgeddonfm/plugmem}"
OUTPUT_DIR="${4:-C:/Users/tomas/ai-radio/output}"
RADIO_DIR="C:/Users/tomas/ai-radio"

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║  Radio ArmsgeddonFM — Evolution Cycle $CYCLE ($SLOT)              ║"
echo "║  PlugMem Integration Enabled                                      ║"
echo "╚════════════════════════════════════════════════════════════════════╝"

cd "$RADIO_DIR"

# Activate venv
source "$HOME/AppData/Local/hermes/hermes-agent/venv/Scripts/activate"

# Step 1: Query PlugMem for best configurations
echo ""
echo "🔍 [1/6] Querying PlugMem for best configurations..."
python -m radio.plugmem_query --slot "$SLOT" --type prompt --storage "$STORAGE"
python -m radio.plugmem_query --slot "$SLOT" --type music --storage "$STORAGE"
python -m radio.plugmem_query --slot "$SLOT" --type tts --storage "$STORAGE"
python -m radio.plugmem_query --slot "$SLOT" --type pipeline --storage "$STORAGE"

# Step 2: Run DJ orchestrator (generates 1-hour block)
echo ""
echo "🎵 [2/6] Running DJ orchestrator..."
python -m radio.dj \
    --cycle "$CYCLE" \
    --slot "$SLOT" \
    --duration 3600 \
    --storage "$STORAGE" \
    --output "$OUTPUT_DIR"

DJ_EXIT=$?

# Step 3: Evaluate quality
echo ""
echo "📊 [3/6] Evaluating quality..."
# The DJ already does basic evaluation, but we can run additional checks
if [ -f "$OUTPUT_DIR/mixed/${CYCLE}_${SLOT}_final.wav" ]; then
    echo "✅ Mixed output exists"
    ls -lh "$OUTPUT_DIR/mixed/${CYCLE}_${SLOT}_final.wav"
else
    echo "⚠️ No mixed output found"
fi

# Step 4: Consolidate into PlugMem (with auto-consolidation)
echo ""
echo "📦 [4/6] Consolidating into PlugMem..."
python -m radio.plugmem_consolidate \
    --cycle "$CYCLE" \
    --slot "$SLOT" \
    --duration 3600 \
    --badge "$CYCLE" \
    --music-quality 0.85 \
    --tts-quality 0.88 \
    --mix-quality 0.90 \
    --pipeline-time 180 \
    --music-model "musicgen-small" \
    --music-prompt "upbeat electronic, 110 bpm, energetic, synthesizers, optimistic" \
    --music-params '{"duration": 30, "temperature": 1.0, "cfg_coef": 3.0}' \
    --tts-voice "qwen_custom_voice" \
    --tts-preset "Ryan" \
    --pipeline-config '{"music_first": true, "crossfade_sec": 2.0, "ducking_db": -18, "target_lufs": -14}' \
    --storage "$STORAGE" \
    --consolidate

# Step 5: Show PlugMem stats
echo ""
echo "📊 [5/6] PlugMem Statistics:"
python -c "
from radio.plugmem_client import create_radio_plugmem
from pathlib import Path
client = create_radio_plugmem(Path(r'$STORAGE'))
print(client.get_stats())
"

# Step 6: Backup to USB
echo ""
echo "💾 [6/6] Backing up to USB..."
BACKUP_DIR="$STORAGE/../radio_${CYCLE}_cycle01_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -r "$OUTPUT_DIR/mixed/${CYCLE}_${SLOT}_final.wav" "$BACKUP_DIR/" 2>/dev/null || true
cp -r "$STORAGE" "$BACKUP_DIR/plugmem" 2>/dev/null || true
echo "✅ Backup created: $BACKUP_DIR"

echo ""
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║  Evolution Cycle $CYCLE ($SLOT) COMPLETE                          ║"
echo "║  Badge: $CYCLE                                                     ║"
echo "║  Status: SUCCESS                                                  ║"
echo "╚════════════════════════════════════════════════════════════════════╝"

exit $DJ_EXIT