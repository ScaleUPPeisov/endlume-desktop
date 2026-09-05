#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
TMP="$(mktemp -d /tmp/endlume-852-x265.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
BG="$TMP/bg.png"; DUR=8; FPS=60; GOP=$((DUR*FPS))
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=1920x1080:rate=1' -frames:v 1 -y "$BG"
FC="[0:v]scale=1920:1080:flags=lanczos+accurate_rnd,format=yuv420p[bg];[1:v]format=rgba,colorchannelmixer=aa=0.30[fx];[bg][fx]overlay=x='mod(t*120,1280)':y=600:shortest=1[outv]"
now(){ python3 - <<'PY'
import time; print(time.monotonic())
PY
}
enc(){
  local name="$1"; shift; local out="$TMP/$name.mp4"; local a b sec br
  a="$(now)"
  "$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate "$FPS" -i "$BG" -f lavfi -i 'testsrc2=size=640x360:rate=60' -filter_complex "$FC" -map '[outv]' -t "$DUR" -an "$@" -g "$GOP" -tag:v hvc1 -pix_fmt yuv420p -y "$out"
  b="$(now)"
  sec="$(python3 - "$a" "$b" <<'PY'
import sys; print(f'{float(sys.argv[2])-float(sys.argv[1]):.3f}')
PY
)"
  br="$($FFPROBE -v error -show_entries format=bit_rate -of default=nw=1:nk=1 "$out" | tr -d '\r')"; [[ "$br" =~ ^[0-9]+$ ]] || br=0
  echo -e "$name\t$sec\t$((br/1000))"
}
enc q100 -c:v hevc_videotoolbox -realtime 1 -prio_speed 0 -power_efficient 0 -q:v 100 -b:v 500k -maxrate 12M -bufsize 64M > "$TMP/ref.row"
REF="$TMP/q100.mp4"
echo -e 'PROFILE\tSECONDS\tKBPS\tSSIM_TO_Q100\tPROJECTED_2H12_WITH_320K_MB'
read -r name sec kbps < <(tr '\t' ' ' < "$TMP/ref.row")
proj="$(python3 - "$kbps" <<'PY'
import sys; print(f'{(float(sys.argv[1])+320)*7920/8/1000:.1f}')
PY
)"; echo -e "$name\t$sec\t$kbps\t1.000000\t$proj"
for cap in 500 450 400 380 350 320; do
  row="$(enc x265_crf18_${cap} -c:v libx265 -preset ultrafast -crf 18 -maxrate ${cap}k -bufsize 4M -x265-params "log-level=error:keyint=$GOP:min-keyint=$GOP:scenecut=0:open-gop=0:aq-mode=3:aq-strength=1.0:vbv-init=1.0")"
  IFS=$'\t' read -r n sec kbps <<< "$row"
  SSIM="$($FFMPEG -hide_banner -i "$REF" -i "$TMP/$n.mp4" -lavfi '[0:v]format=yuv420p[a];[1:v]format=yuv420p[b];[a][b]ssim' -f null - 2>&1 | sed -n 's/.*All:\([0-9.]*\).*/\1/p' | tail -1)"; [[ "$SSIM" =~ ^[0-9.]+$ ]] || SSIM=0
  proj="$(python3 - "$kbps" <<'PY'
import sys; print(f'{(float(sys.argv[1])+320)*7920/8/1000:.1f}')
PY
)"
  echo -e "$n\t$sec\t$kbps\t$SSIM\t$proj"
done
echo 'PASS: x265 ultrafast physical sweep complete.'
