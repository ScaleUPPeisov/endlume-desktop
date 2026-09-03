#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
TMP="$(mktemp -d /tmp/endlume-vt-sweep.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
REF="$TMP/reference.png"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=1920x1080:rate=1' -frames:v 1 -y "$REF"

printf 'PROFILE\tTIME_S\tSSIM\tVIDEO_KBPS\tSIZE_MIB\n'
for Q in 70 80 90 95 100; do
  OUT="$TMP/q${Q}.mp4"; DEC="$TMP/q${Q}.png"
  START="$(python3 - <<'PY'
import time;print(time.monotonic())
PY
)"
  "$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 60 -i "$REF" -t 12 -an \
    -c:v hevc_videotoolbox -realtime 1 -prio_speed 0 -power_efficient 0 \
    -q:v "$Q" -maxrate 12M -bufsize 64M -g 720 -tag:v hvc1 -pix_fmt yuv420p -y "$OUT"
  END="$(python3 - <<'PY'
import time;print(time.monotonic())
PY
)"
  SEC="$(python3 - "$START" "$END" <<'PY'
import sys;print(f'{float(sys.argv[2])-float(sys.argv[1]):.3f}')
PY
)"
  "$FFMPEG" -hide_banner -loglevel error -i "$OUT" -frames:v 1 -y "$DEC"
  SSIM="$($FFMPEG -hide_banner -i "$REF" -i "$DEC" -filter_complex '[0:v]format=yuv420p[a];[1:v]format=yuv420p[b];[a][b]ssim' -frames:v 1 -f null - 2>&1 | sed -n 's/.*All:\([0-9.]*\).*/\1/p' | tail -1)"
  BR="$($FFPROBE -v error -select_streams v:0 -show_entries stream=bit_rate -of default=nw=1:nk=1 "$OUT" | tr -d '\r')"
  [[ "$BR" =~ ^[0-9]+$ ]] || BR=0
  KBPS=$((BR/1000))
  SZ="$(python3 - "$OUT" <<'PY'
import os,sys;print(f'{os.path.getsize(sys.argv[1])/1024/1024:.3f}')
PY
)"
  printf 'q=%s\t%s\t%s\t%s\t%s\n' "$Q" "$SEC" "$SSIM" "$KBPS" "$SZ"
done

# Also test constrained-quality forms: quality mode plus a target average. Some
# VideoToolbox builds interpret this better than pure ABR for the first I-frame.
for Q in 90 100; do
  OUT="$TMP/q${Q}-b500.mp4"; DEC="$TMP/q${Q}-b500.png"
  START="$(python3 - <<'PY'
import time;print(time.monotonic())
PY
)"
  "$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 60 -i "$REF" -t 12 -an \
    -c:v hevc_videotoolbox -realtime 1 -prio_speed 0 -power_efficient 0 \
    -q:v "$Q" -b:v 500k -maxrate 12M -bufsize 64M -g 720 -tag:v hvc1 -pix_fmt yuv420p -y "$OUT"
  END="$(python3 - <<'PY'
import time;print(time.monotonic())
PY
)"
  SEC="$(python3 - "$START" "$END" <<'PY'
import sys;print(f'{float(sys.argv[2])-float(sys.argv[1]):.3f}')
PY
)"
  "$FFMPEG" -hide_banner -loglevel error -i "$OUT" -frames:v 1 -y "$DEC"
  SSIM="$($FFMPEG -hide_banner -i "$REF" -i "$DEC" -filter_complex '[0:v]format=yuv420p[a];[1:v]format=yuv420p[b];[a][b]ssim' -frames:v 1 -f null - 2>&1 | sed -n 's/.*All:\([0-9.]*\).*/\1/p' | tail -1)"
  BR="$($FFPROBE -v error -select_streams v:0 -show_entries stream=bit_rate -of default=nw=1:nk=1 "$OUT" | tr -d '\r')"; [[ "$BR" =~ ^[0-9]+$ ]] || BR=0
  KBPS=$((BR/1000)); SZ="$(python3 - "$OUT" <<'PY'
import os,sys;print(f'{os.path.getsize(sys.argv[1])/1024/1024:.3f}')
PY
)"
  printf 'q=%s+b500\t%s\t%s\t%s\t%s\n' "$Q" "$SEC" "$SSIM" "$KBPS" "$SZ"
done
