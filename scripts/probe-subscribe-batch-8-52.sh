#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
TMP="$(mktemp -d /tmp/endlume-852-sub-batch.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
BG="$TMP/bg.png"; BASE="$TMP/base.mp4"; SUB="$TMP/sub.mov"

now(){ python3 - <<'PY'
import time
print(time.monotonic())
PY
}
elapsed(){ python3 - "$1" "$2" <<'PY'
import sys
print(f'{float(sys.argv[2])-float(sys.argv[1]):.3f}')
PY
}

"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=1920x1080:rate=1' -frames:v 1 -y "$BG"
# Ten-second base variant, matching ENDLUME one-still + Effects architecture.
"$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 60 -i "$BG" -f lavfi -i 'testsrc2=size=640x360:rate=60' \
  -filter_complex "[0:v]format=yuv420p[bg];[1:v]format=rgba,colorchannelmixer=aa=0.25[fx];[bg][fx]overlay=x='mod(t*100,1280)':y=650:shortest=1[outv]" \
  -map '[outv]' -t 10 -an -c:v hevc_videotoolbox -realtime 1 -prio_speed 0 -power_efficient 0 -q:v 100 -b:v 500k -maxrate 12M -bufsize 64M -g 600 -tag:v hvc1 -pix_fmt yuv420p -y "$BASE"
# A small RGBA-like Subscribe animation source. Chroma-keying + overlay is intentionally CPU filter work.
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x00ff00:s=640x180:r=60:d=5' -f lavfi -i 'testsrc2=size=260x100:rate=60:d=5' \
  -filter_complex "[0:v][1:v]overlay=x='20+mod(t*80,300)':y=40:shortest=1[outv]" -map '[outv]' -t 5 -c:v qtrle -pix_fmt argb -y "$SUB"

PHASES=(0.0 1.2 2.4 3.6 4.8 6.0)
LEN=4.0
PROFILE=(-c:v hevc_videotoolbox -realtime 1 -prio_speed 0 -power_efficient 0 -q:v 100 -b:v 500k -maxrate 12M -bufsize 64M -g 240 -tag:v hvc1 -pix_fmt yuv420p)

serial0="$(now)"
for idx in "${!PHASES[@]}"; do
  p="${PHASES[$idx]}"
  "$FFMPEG" -hide_banner -loglevel error -stream_loop -1 -ss "$p" -i "$BASE" -i "$SUB" \
    -filter_complex "[1:v]fps=60,format=rgba,chromakey=0x00ff00:0.10:0.04,scale=640:180[sub];[0:v]setpts=PTS-STARTPTS[bg];[bg][sub]overlay=x='(W-w)/2':y='H-h-90':shortest=1:eof_action=repeat[outv]" \
    -map '[outv]' -t "$LEN" -an "${PROFILE[@]}" -y "$TMP/serial-$idx.mp4"
done
serial1="$(now)"
SERIAL="$(elapsed "$serial0" "$serial1")"

declare -a CMD
CMD=("$FFMPEG" -hide_banner -loglevel error)
# Inputs: base/sub pair per phase so every output has the exact same seek and effect offset semantics as serial mode.
for p in "${PHASES[@]}"; do
  CMD+=(-stream_loop -1 -ss "$p" -i "$BASE" -i "$SUB")
done
for idx in "${!PHASES[@]}"; do
  b=$((idx*2)); s=$((idx*2+1))
  CMD+=(-filter_complex "[$s:v]fps=60,format=rgba,chromakey=0x00ff00:0.10:0.04,scale=640:180[s$idx];[$b:v]setpts=PTS-STARTPTS[b$idx];[b$idx][s$idx]overlay=x='(W-w)/2':y='H-h-90':shortest=1:eof_action=repeat[o$idx]")
done
for idx in "${!PHASES[@]}"; do
  CMD+=(-map "[o$idx]" -t "$LEN" -an "${PROFILE[@]}" -y "$TMP/batch-$idx.mp4")
done
batch0="$(now)"
"${CMD[@]}"
batch1="$(now)"
BATCH="$(elapsed "$batch0" "$batch1")"

echo -e 'MODE\tSECONDS\tSEGMENTS'
echo -e "serial\t$SERIAL\t${#PHASES[@]}"
echo -e "batch\t$BATCH\t${#PHASES[@]}"

MIN=1.0
for idx in "${!PHASES[@]}"; do
  S="$TMP/serial-$idx.mp4"; B="$TMP/batch-$idx.mp4"
  test -s "$S"; test -s "$B"
  SSIM="$($FFMPEG -hide_banner -i "$S" -i "$B" -lavfi '[0:v]format=yuv420p[a];[1:v]format=yuv420p[b];[a][b]ssim' -f null - 2>&1 | sed -n 's/.*All:\([0-9.]*\).*/\1/p' | tail -1)"
  echo "phase=${PHASES[$idx]} serial-vs-batch SSIM=$SSIM"
  python3 - "$SSIM" <<'PY'
import sys
v=float(sys.argv[1]);
if v < 0.995: raise SystemExit(f'batch fidelity regression: {v:.6f}')
PY
done
python3 - "$SERIAL" "$BATCH" <<'PY'
import sys
s,b=map(float,sys.argv[1:])
print(f'BATCH_SPEEDUP={s/b:.2f}x')
if b >= s*0.90: raise SystemExit(f'batch does not materially improve wall time: serial={s:.3f}s batch={b:.3f}s')
PY

echo 'PASS: exact multi-phase Subscribe batch keeps visual output and materially reduces wall time.'
