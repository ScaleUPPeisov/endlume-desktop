#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
TMP="$(mktemp -d /tmp/endlume-vt-cap-sweep.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
REF="$TMP/reference.png"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=1920x1080:rate=1' -frames:v 1 -y "$REF"

printf 'PROFILE\tSTATIC_S\tSSIM\tDYNAMIC_S\tDYNAMIC_KBPS\n'
for SPEC in '70:750k' '80:750k' '90:750k' '100:750k' '100:1M' '100:1500k'; do
  Q="${SPEC%%:*}"; MAX="${SPEC#*:}"
  KEY="q${Q}-max${MAX}"
  OUT="$TMP/${KEY}-static.mp4"; DEC="$TMP/${KEY}.png"; DYN="$TMP/${KEY}-dynamic.mp4"
  S0="$(python3 - <<'PY'
import time;print(time.monotonic())
PY
)"
  "$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 60 -i "$REF" -t 12 -an \
    -c:v hevc_videotoolbox -realtime 1 -prio_speed 0 -power_efficient 0 \
    -q:v "$Q" -b:v 500k -maxrate "$MAX" -bufsize 64M -g 720 -tag:v hvc1 -pix_fmt yuv420p -y "$OUT"
  S1="$(python3 - <<'PY'
import time;print(time.monotonic())
PY
)"
  STATIC_SEC="$(python3 - "$S0" "$S1" <<'PY'
import sys;print(f'{float(sys.argv[2])-float(sys.argv[1]):.3f}')
PY
)"
  "$FFMPEG" -hide_banner -loglevel error -i "$OUT" -frames:v 1 -y "$DEC"
  SSIM="$($FFMPEG -hide_banner -i "$REF" -i "$DEC" -filter_complex '[0:v]format=yuv420p[a];[1:v]format=yuv420p[b];[a][b]ssim' -frames:v 1 -f null - 2>&1 | sed -n 's/.*All:\([0-9.]*\).*/\1/p' | tail -1)"

  FC="[0:v]scale=1920:1080:flags=lanczos,format=yuv420p[bg];[1:v]format=rgba,colorchannelmixer=aa=0.30[ov];[bg][ov]overlay=x='mod(t*120,1280)':y=360:shortest=1[outv]"
  D0="$(python3 - <<'PY'
import time;print(time.monotonic())
PY
)"
  "$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 60 -i "$REF" -f lavfi -i 'testsrc2=size=640x360:rate=60' \
    -filter_complex "$FC" -map '[outv]' -t 20 -an \
    -c:v hevc_videotoolbox -realtime 1 -prio_speed 0 -power_efficient 0 \
    -q:v "$Q" -b:v 500k -maxrate "$MAX" -bufsize 64M -g 1200 -tag:v hvc1 -pix_fmt yuv420p -y "$DYN"
  D1="$(python3 - <<'PY'
import time;print(time.monotonic())
PY
)"
  DYN_SEC="$(python3 - "$D0" "$D1" <<'PY'
import sys;print(f'{float(sys.argv[2])-float(sys.argv[1]):.3f}')
PY
)"
  BR="$($FFPROBE -v error -select_streams v:0 -show_entries stream=bit_rate -of default=nw=1:nk=1 "$DYN" | tr -d '\r')"; [[ "$BR" =~ ^[0-9]+$ ]] || BR=0
  KBPS=$((BR/1000))
  printf '%s\t%s\t%s\t%s\t%s\n' "$KEY" "$STATIC_SEC" "$SSIM" "$DYN_SEC" "$KBPS"
done
