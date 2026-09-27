#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
fail(){ echo "FAIL: $1" >&2; exit 1; }
pass(){ echo "PASS: $1"; }

python3 -m py_compile scripts/repair-hybrid-patcher-8-29.py scripts/apply-version-8-30.py scripts/apply-hybrid-fidelity-8-28.py
pass '8.30 Python patch stack compiles'

# Reuse the full 4K / exact-MP3 / MOV / Effects+Subscribe runtime gate.
scripts/validate-release-8-29.sh "$FFMPEG" "$FFPROBE"

# Installation drift gates.
if grep -Fq "8.28: Subscribe encoder marker missing" scripts/apply-hybrid-fidelity-8-28.py; then
  fail 'brittle Subscribe patch failure branch still present after repair'
else
  pass 'Subscribe patcher is drift-safe'
fi
grep -Fq '"-crf","22"' src-tauri/src/render.rs || fail 'CRF22 hybrid fidelity profile missing'
grep -Fq 'audio-original-clean.mp3' src-tauri/src/render.rs || fail 'exact MP3 rebuild missing'
grep -Fq 'probe_audio_decodes(app,out)' src-tauri/src/render.rs || fail 'final real audio decode check missing'
grep -Fq 'unique_output_ext(&out_dir,&job.project.name,"mov")' src-tauri/src/render.rs || fail 'MOV exact-audio output missing'
grep -Fq "chooseVideo('subscribe')" src/pages/Editors.tsx || fail 'Subscribe managed import missing'
pass '8.30 static stability gates passed'

echo 'ENDLUME 8.30 release gate passed.'
