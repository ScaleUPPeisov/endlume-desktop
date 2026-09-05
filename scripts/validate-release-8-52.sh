#!/bin/bash
set -Eeuo pipefail
ROOT="${1:-.}"
FFMPEG="${2:-ffmpeg}"
FFPROBE="${3:-ffprobe}"
R="$ROOT/src-tauri/src/render.rs"
C="$ROOT/src-tauri/Cargo.toml"
fail(){ echo "FAIL 8.52: $1" >&2; exit 1; }
pass(){ echo "PASS: $1"; }
[[ -f "$R" && -f "$C" ]] || fail 'effective source missing'

# Production contract. These checks specifically cover the two paths that 8.50/8.51 gates missed.
grep -Fq 'RENDER_CACHE_GENERATION:&str="8.52-crf18-size360-v1"' "$R" || fail '8.52 render cache generation missing'
grep -Fq 'VISUAL_PLAN_CACHE_GENERATION:&str="8.52-parallel-composite-v1"' "$R" || fail '8.52 visual plan generation missing'
grep -Fq 'fn hybrid_video_kbps(_s:&RenderSettings)->u64{360}' "$R" || fail '360k smart budget missing'
grep -Fq '"-crf","18","-maxrate","360k","-bufsize","4M"' "$R" || fail 'CRF18/360k quality profile missing'
grep -Fq 'attempt==1&&encoder_works(app,"libx265")' "$R" || fail 'x265 fidelity-first smart selector missing'
grep -Fq 'smart_composite_encoder_args(job,encoder,master_duration)' "$R" || fail 'Effects still bypass smart fidelity'
grep -Fq 'smart_composite_encoder_args(job,encoder,len)' "$R" || fail 'Subscribe still bypasses smart fidelity'
grep -Fq '8.52 PARALLEL_START' "$R" || fail 'parallel Subscribe planner missing'
grep -Fq 'tokio::join!' "$R" || fail 'parallel execution missing'
grep -Fq 'features = ["time", "macros", "rt-multi-thread"]' "$C" || fail 'tokio macros runtime features missing'
grep -Fq 'resolved_job.settings.width=1920;' "$R" || fail '1920 lock lost'
grep -Fq 'resolved_job.settings.height=1080;' "$R" || fail '1080 lock lost'
grep -Fq 'resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};' "$R" || fail 'CFR 30/60 normalization lost'
grep -Fq 'let duration_mode=if smart_repeat_project(job){"whole-track"}else{job.settings.duration_mode.as_str()};' "$R" || fail 'whole-song policy lost'
pass '8.52 smart composite path no longer uses generic UI Mbps and has four-lane Subscribe scheduling'

TMP="$(mktemp -d /tmp/endlume-852-gate.XXXXXX)"; trap 'rm -rf "$TMP"' EXIT
BG="$TMP/bg.png"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=1920x1080:rate=1' -frames:v 1 -y "$BG"
FC="[0:v]scale=1920:1080:flags=lanczos+accurate_rnd,format=yuv420p[bg];[1:v]format=rgba,colorchannelmixer=aa=0.30[fx];[bg][fx]overlay=x='mod(t*120,1280)':y=600:shortest=1[outv]"

# Compare the exact same animated composite against the current q100 visual reference.
REF="$TMP/q100-reference.mp4"; CAND="$TMP/x265-360.mp4"
"$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 60 -i "$BG" -f lavfi -i 'testsrc2=size=640x360:rate=60' \
  -filter_complex "$FC" -map '[outv]' -t 8 -an \
  -c:v hevc_videotoolbox -realtime 1 -prio_speed 0 -power_efficient 0 -q:v 100 -b:v 500k -maxrate 12M -bufsize 64M -g 480 -tag:v hvc1 -pix_fmt yuv420p -y "$REF"
START="$(python3 -c 'import time;print(time.monotonic())')"
"$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 60 -i "$BG" -f lavfi -i 'testsrc2=size=640x360:rate=60' \
  -filter_complex "$FC" -map '[outv]' -t 8 -an \
  -c:v libx265 -preset ultrafast -crf 18 -maxrate 360k -bufsize 4M \
  -x265-params 'log-level=error:keyint=480:min-keyint=480:scenecut=0:open-gop=0:aq-mode=3:aq-strength=1.0:vbv-init=1.0' \
  -tag:v hvc1 -pix_fmt yuv420p -y "$CAND"
END="$(python3 -c 'import time;print(time.monotonic())')"
SSIM="$($FFMPEG -hide_banner -i "$REF" -i "$CAND" -lavfi '[0:v]format=yuv420p[a];[1:v]format=yuv420p[b];[a][b]ssim' -f null - 2>&1 | sed -n 's/.*All:\([0-9.]*\).*/\1/p' | tail -1)"
FIRST="$($FFMPEG -hide_banner -i "$REF" -i "$CAND" -lavfi "[0:v]select='eq(n,0)',format=yuv420p[a];[1:v]select='eq(n,0)',format=yuv420p[b];[a][b]ssim" -frames:v 1 -f null - 2>&1 | sed -n 's/.*All:\([0-9.]*\).*/\1/p' | tail -1)"
python3 - "$START" "$END" "$SSIM" "$FIRST" <<'PY'
import sys
sec=float(sys.argv[2])-float(sys.argv[1]); whole=float(sys.argv[3]); first=float(sys.argv[4])
print(f'PASS: CRF18/360 candidate 8s encode={sec:.3f}s whole-SSIM={whole:.6f} first-frame-SSIM={first:.6f}')
if first < 0.995: raise SystemExit(f'FAIL: image fidelity below 0.995: {first:.6f}')
if whole < 0.985: raise SystemExit(f'FAIL: animated composite fidelity below 0.985: {whole:.6f}')
if sec > 12: raise SystemExit(f'FAIL: 8s smart composite too slow: {sec:.3f}s')
PY

# Sixty seconds amortizes the protected I-frame and is representative of the looped Effects master.
LONG="$TMP/x265-360-60s.mp4"
"$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 60 -i "$BG" -f lavfi -i 'testsrc2=size=640x360:rate=60' \
  -filter_complex "$FC" -map '[outv]' -t 60 -an \
  -c:v libx265 -preset ultrafast -crf 18 -maxrate 360k -bufsize 4M \
  -x265-params 'log-level=error:keyint=3600:min-keyint=3600:scenecut=0:open-gop=0:aq-mode=3:aq-strength=1.0:vbv-init=1.0' \
  -tag:v hvc1 -pix_fmt yuv420p -y "$LONG"
VBR="$($FFPROBE -v error -show_entries format=bit_rate -of default=nw=1:nk=1 "$LONG" | tr -d '\r')"
python3 - "$VBR" <<'PY'
import sys
v=int(sys.argv[1]); kb=v/1000
# 2h12 worst-case envelope with 320k audio and a small container margin.
seconds=2*3600+12*60
projected=(v+320_000)*seconds/8
print(f'PASS: 60s composite bitrate={kb:.1f}kbps projected 2h12 + 320k audio={projected/1e6:.1f}MB')
if projected > 700_000_000: raise SystemExit(f'FAIL: projected output exceeds 700 MB: {projected/1e6:.1f}')
if v > 410_000: raise SystemExit(f'FAIL: loop master bitrate too high: {kb:.1f}kbps')
PY

echo '✅ ENDLUME 8.52 REAL COMPOSITE FIDELITY / SIZE GATE PASS'
