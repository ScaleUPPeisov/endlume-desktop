#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
TMP="$(mktemp -d /tmp/endlume-852-profile.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
BG="$TMP/bg.png"

"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=1920x1080:rate=1' -frames:v 1 -y "$BG"
FC="[0:v]scale=1920:1080:flags=lanczos,format=yuv420p[bg];[1:v]format=rgba,colorchannelmixer=aa=0.30[fx];[bg][fx]overlay=x='mod(t*120,1280)':y=600:shortest=1[outv]"
DUR=20
FPS=60
GOP=$((DUR*FPS))

now(){ python3 - <<'PY'
import time
print(time.monotonic())
PY
}

encode(){
  local name="$1"; shift
  local out="$TMP/$name.mp4"
  local t0="$(now)"
  "$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate "$FPS" -i "$BG" -f lavfi -i 'testsrc2=size=640x360:rate=60' \
    -filter_complex "$FC" -map '[outv]' -t "$DUR" -an "$@" -g "$GOP" -tag:v hvc1 -pix_fmt yuv420p -y "$out"
  local t1="$(now)"
  local sec="$(python3 - "$t0" "$t1" <<'PY'
import sys
print(f'{float(sys.argv[2])-float(sys.argv[1]):.3f}')
PY
)"
  local br="$($FFPROBE -v error -select_streams v:0 -show_entries stream=bit_rate -of default=nw=1:nk=1 "$out" | tr -d '\r')"
  [[ "$br" =~ ^[0-9]+$ ]] || br=0
  local kbps=$((br/1000))
  printf '%s\t%s\t%s\n' "$name" "$sec" "$kbps"
}

# Current 8.51 visual quality reference.
encode current_q100 \
  -c:v hevc_videotoolbox -realtime 1 -prio_speed 0 -power_efficient 0 \
  -q:v 100 -b:v 500k -maxrate 12M -bufsize 64M > "$TMP/current.row"
REF="$TMP/current_q100.mp4"

echo -e 'PROFILE\tSECONDS\tVIDEO_KBPS\tSSIM_TO_CURRENT\tPROJECTED_2H05_MB'
cat "$TMP/current.row" | while IFS=$'\t' read -r name sec kbps; do
  proj="$(python3 - "$kbps" <<'PY'
import sys
v=float(sys.argv[1]); print(f'{(v+320.0)*7500/8/1000:.1f}')
PY
)"
  echo -e "$name\t$sec\t$kbps\t1.000000\t$proj"
done

run_candidate(){
  local name="$1"; shift
  local row
  row="$(encode "$name" "$@")"
  IFS=$'\t' read -r n sec kbps <<< "$row"
  local cand="$TMP/$name.mp4"
  local ssim
  ssim="$($FFMPEG -hide_banner -i "$REF" -i "$cand" -lavfi '[0:v]format=yuv420p[a];[1:v]format=yuv420p[b];[a][b]ssim' -f null - 2>&1 | sed -n 's/.*All:\([0-9.]*\).*/\1/p' | tail -1)"
  [[ "$ssim" =~ ^[0-9.]+$ ]] || ssim=0
  local proj
  proj="$(python3 - "$kbps" <<'PY'
import sys
v=float(sys.argv[1]); print(f'{(v+320.0)*7500/8/1000:.1f}')
PY
)"
  echo -e "$n\t$sec\t$kbps\t$ssim\t$proj"
}

# VideoToolbox quality-mode caps. These tell us whether q100 can be retained at a real size cap.
run_candidate vt_q100_750 \
  -c:v hevc_videotoolbox -realtime 1 -prio_speed 0 -power_efficient 0 -q:v 100 -b:v 400k -maxrate 750k -bufsize 8M
run_candidate vt_q90_750 \
  -c:v hevc_videotoolbox -realtime 1 -prio_speed 0 -power_efficient 0 -q:v 90 -b:v 400k -maxrate 750k -bufsize 8M
run_candidate vt_q80_750 \
  -c:v hevc_videotoolbox -realtime 1 -prio_speed 0 -power_efficient 0 -q:v 80 -b:v 400k -maxrate 750k -bufsize 8M

# True ABR options; needed if VideoToolbox ignores bitrate while q:v is set.
run_candidate vt_abr450 \
  -c:v hevc_videotoolbox -realtime 1 -prio_speed 0 -power_efficient 0 -b:v 450k -maxrate 750k -bufsize 8M
run_candidate vt_abr400 \
  -c:v hevc_videotoolbox -realtime 1 -prio_speed 0 -power_efficient 0 -b:v 400k -maxrate 700k -bufsize 8M

# Proven software fidelity family from 8.49, measured with faster presets too.
run_candidate x265_fast_crf18_450 \
  -c:v libx265 -preset fast -crf 18 -maxrate 450k -bufsize 4M -x265-params log-level=error
run_candidate x265_veryfast_crf18_450 \
  -c:v libx265 -preset veryfast -crf 18 -maxrate 450k -bufsize 4M -x265-params log-level=error
run_candidate x265_faster_crf18_450 \
  -c:v libx265 -preset faster -crf 18 -maxrate 450k -bufsize 4M -x265-params log-level=error

echo 'PASS: 8.52 physical profile sweep complete; no production profile changed yet.'
