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

grep -Fq 'resolved_job.settings.width=1920;' "$RUST" || fail 'runtime width is not locked to 1920'
grep -Fq 'resolved_job.settings.height=1080;' "$RUST" || fail 'runtime height is not locked to 1080'
grep -Fq 'resolved_job.settings.crossfade_sec=0.0' "$RUST" || fail 'one-image MP3-copy profile no longer disables crossfade'
grep -Fq 'audio-original-clean.mp3' "$RUST" || fail 'original MP3 bitstream-copy path missing'
grep -Fq 'flags=lanczos+accurate_rnd' "$RUST" || fail 'Lanczos source scaling missing'
grep -Fq 'attempt==1&&encoder_works(app,"libx265")' "$RUST" || fail 'x265-first selector missing'
grep -Fq '"-crf","18"' "$RUST" || fail 'CRF18 first-frame quality profile missing'
grep -Fq '"-maxrate","500k"' "$RUST" || fail '500k dynamic cap missing'
grep -Fq '"-bufsize","4M"' "$RUST" || fail '4M VBV buffer missing'
grep -Fq "width:1920,height:1080,fps:30,codec:'h265'" "$STORE" || fail 'UI defaults are not 1080p/30/HEVC'
grep -Fq 'version:4,migrate:' "$STORE" || fail 'persisted settings migration v4 missing'
grep -Fq '1080P FULL HD' "$PROJECT" || fail '1080p UI option missing'
if grep -Eq '"version": "1\.0\.0-alpha\.8\.(36|37)"' "$PKG"; then :; else fail 'package version is not 8.36/8.37'; fi
pass '1080p Fidelity Lock wiring + original MP3 path are present'

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=1920x1080:rate=1' -frames:v 1 -y "$TMP/base.png"
START="$(python3 - <<'PY'
import time
print(time.time())
PY
)"
"$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 30 -i "$TMP/base.png" -t 12 -an \
  -c:v libx265 -preset ultrafast -crf 18 -maxrate 500k -bufsize 4M \
  -x265-params 'keyint=360:min-keyint=360:scenecut=0:open-gop=0:aq-mode=3:aq-strength=1.0:vbv-init=1.0' \
  -tag:v hvc1 -pix_fmt yuv420p -y "$TMP/static.mp4"
END="$(python3 - <<'PY'
import time
print(time.time())
PY
)"
DIM="$("$FFPROBE" -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "$TMP/static.mp4")"
[[ "$DIM" == "1920x1080" ]] || fail "encoded dimensions are $DIM instead of 1920x1080"
pass 'encoded master is exactly 1920x1080'

"$FFMPEG" -hide_banner -loglevel info -i "$TMP/base.png" -i "$TMP/static.mp4" \
  -lavfi "[0:v]format=yuv420p[ref];[1:v]select='eq(n,0)',format=yuv420p[enc];[ref][enc]ssim" \
  -frames:v 1 -f null - 2>"$TMP/ssim.log" || fail 'SSIM comparison failed'
SSIM="$(grep -oE 'All:[0-9.]+' "$TMP/ssim.log" | tail -1 | cut -d: -f2)"
[[ -n "$SSIM" ]] || fail 'first-frame SSIM metric missing'
python3 - "$SSIM" <<'PY'
import sys
v=float(sys.argv[1])
print(f'PASS: first-frame SSIM = {v:.6f}')
if v < 0.995:
    raise SystemExit(f'FAIL: first-frame quality below 0.995: {v:.6f}')
PY
python3 - "$START" "$END" <<'PY'
import sys
sec=float(sys.argv[2])-float(sys.argv[1])
print(f'PASS: 12s 1080p x265 master encoded in {sec:.2f}s')
if sec > 30:
    raise SystemExit(f'FAIL: short master is too slow for <=1 minute target: {sec:.2f}s')
PY

"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=640x360:rate=30' -t 12 -c:v libx264 -preset ultrafast -y "$TMP/fx.mp4"
"$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 30 -i "$TMP/base.png" -stream_loop -1 -i "$TMP/fx.mp4" \
  -filter_complex '[0:v]setsar=1[b];[1:v]scale=640:360[fx];[b][fx]overlay=x=50:y=600:shortest=1:eof_action=repeat,format=yuv420p[v]' \
  -map '[v]' -t 12 -an -c:v libx265 -preset ultrafast -crf 18 -maxrate 500k -bufsize 4M \
  -x265-params 'keyint=360:min-keyint=360:scenecut=0:open-gop=0:aq-mode=3:aq-strength=1.0:vbv-init=1.0' \
  -tag:v hvc1 -pix_fmt yuv420p -y "$TMP/motion.mp4"
VBR="$("$FFPROBE" -v error -show_entries format=bit_rate -of default=nw=1:nk=1 "$TMP/motion.mp4")"
python3 - "$VBR" <<'PY'
import sys
v=int(sys.argv[1])
print(f'PASS: busy-overlay master bitrate = {v/1000:.1f} kbit/s')
if v > 740_000:
    raise SystemExit(f'FAIL: busy-overlay bitrate too high: {v}')
seconds=2*3600+2*60+3
payload=(v+320_000)*seconds/8
print(f'PASS: projected 2:02:03 payload with 320k MP3 = {payload/1e6:.1f} MB')
if payload > 1_000_000_000:
    raise SystemExit(f'FAIL: projected payload exceeds 1 GB: {payload}')
PY

echo 'ENDLUME 8.36 exact-1080p image-quality/size/speed gate passed.'
