#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
fail(){ echo "FAIL: $1" >&2; exit 1; }
pass(){ echo "PASS: $1"; }

RUST=src-tauri/src/render.rs
STORE=src/store.ts
PROJECT=src/pages/ProjectPage.tsx
PKG=package.json
for f in "$RUST" "$STORE" "$PROJECT" "$PKG"; do test -f "$f" || fail "missing $f"; done

grep -Fq 'resolved_job.settings.fps=resolved_job.settings.fps.min(30)' "$RUST" || fail 'one-image render is not clamped to <=30 FPS'
grep -Fq 'resolved_job.settings.crossfade_sec=0.0' "$RUST" || fail 'Strict Fidelity still permits ALAC-triggering crossfade'
grep -Fq 'resolved_job.settings.normalize_lufs=false' "$RUST" || fail 'Strict Fidelity still permits LUFS processing'
grep -Fq 'resolved_job.ambient=None' "$RUST" || fail 'Strict Fidelity still permits ambient remix'
grep -Fq 'Strict Fidelity: исходную музыку нельзя сохранить bitstream-copy' "$RUST" || fail 'exact MP3 guard missing'
grep -Fq 'audio-original-clean.mp3' "$RUST" || fail 'exact MP3 bitstream-copy path missing'
pass 'Strict Fidelity preserves compatible MP3 without a second lossy generation'

! grep -Fq 'let g=(s.fps.max(1)*2).to_string();' "$RUST" || fail 'old noisy 2-second GOP returned'
grep -Fq 'let frames=(s.fps.max(1) as f64*duration.max(2.0)' "$RUST" || fail 'full-master GOP calculation missing'
grep -Fq '"-bufsize","64M"' "$RUST" || fail '64 MB keyframe buffer missing'
grep -Fq '"-maxrate","12M"' "$RUST" || fail 'I-frame burst ceiling missing'
grep -Fq '0..=1920=>600,1921..=2560=>680,_=>740' "$RUST" || fail 'strict video budget missing'
grep -Fq '"-prio_speed","0"' "$RUST" || fail 'VideoToolbox quality priority missing'
pass 'long-GOP 4K quality profile is active'

grep -Fq "width:3840,height:2160,fps:30,codec:'h265'" "$STORE" || fail 'new default is not 4K/30/HEVC'
grep -Fq "crossfadeSec:0" "$STORE" || fail 'new default crossfade is not off'
grep -Fq "version:3,migrate:" "$STORE" || fail 'persisted 8.34 settings are not migrated'
grep -Fq '"version": "1.0.0-alpha.8.35"' "$PKG" || fail 'package version is not 8.35'
pass 'UI/default settings match Strict Fidelity runtime'

python3 - <<'PY'
for video in (600,680,740):
    total=(video+320)*1000*7200/8
    if total > 0.98e9:
        raise SystemExit(f'FAIL: 2h payload budget too large: {video}k -> {total/1e9:.3f} GB')
    print(f'PASS: 2h payload {video}k video + exact 320k MP3 -> {total/1e9:.3f} GB')
PY

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# A detailed 4K still exercises the failure mode reported by the user: visible
# grain/mosquito noise on a nominally static source image.
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=3840x2160:rate=1' -frames:v 1 -y "$TMP/base.png"
ENC=libx265
if "$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=black:size=640x360:rate=30' -t 0.15 -an -c:v hevc_videotoolbox -f null - >/dev/null 2>&1; then ENC=hevc_videotoolbox; fi
START="$(python3 - <<'PY'
import time
print(time.time())
PY
)"
if [[ "$ENC" == hevc_videotoolbox ]]; then
  "$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 30 -i "$TMP/base.png" -t 12 -an -c:v hevc_videotoolbox -realtime 1 -prio_speed 0 -power_efficient 0 -b:v 740k -maxrate 12M -bufsize 64M -g 360 -tag:v hvc1 -pix_fmt yuv420p -y "$TMP/master.mp4"
else
  "$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 30 -i "$TMP/base.png" -t 12 -an -c:v libx265 -preset ultrafast -crf 16 -x265-params 'keyint=360:min-keyint=360:scenecut=0:open-gop=0' -tag:v hvc1 -pix_fmt yuv420p -y "$TMP/master.mp4"
fi
END="$(python3 - <<'PY'
import time
print(time.time())
PY
)"
"$FFPROBE" -v error -select_streams v:0 -show_entries stream=codec_name,width,height -of csv=p=0 "$TMP/master.mp4" >/dev/null

# Compare the first encoded 4K frame against the source. 0.94 on synthetic
# testsrc2 is deliberately stricter than a simple decode smoke while avoiding
# false failures caused only by RGB->YUV420 conversion.
"$FFMPEG" -hide_banner -loglevel info -i "$TMP/base.png" -i "$TMP/master.mp4" -lavfi "[0:v]format=yuv420p[ref];[1:v]select='eq(n,0)',format=yuv420p[enc];[ref][enc]ssim" -frames:v 1 -f null - 2>"$TMP/ssim.log" || fail '4K SSIM comparison failed'
SSIM="$(grep -oE 'All:[0-9.]+' "$TMP/ssim.log" | tail -1 | cut -d: -f2)"
[[ -n "$SSIM" ]] || fail 'SSIM metric missing'
python3 - "$SSIM" <<'PY'
import sys
v=float(sys.argv[1])
print(f'PASS: first-frame 4K SSIM = {v:.6f}')
if v < 0.94:
    raise SystemExit(f'FAIL: first-frame quality below threshold: {v:.6f}')
PY

python3 - "$START" "$END" "$ENC" <<'PY'
import sys
sec=float(sys.argv[2])-float(sys.argv[1]); enc=sys.argv[3]
print(f'PASS: 12s 4K Strict Fidelity master with {enc} encoded in {sec:.2f}s')
if enc=='hevc_videotoolbox' and sec>45:
    raise SystemExit(f'FAIL: VideoToolbox 4K master too slow for 1-minute target: {sec:.2f}s')
PY

echo 'ENDLUME 8.35 Strict Fidelity size/speed/image/audio gate passed.'
