#!/bin/bash
set -euo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

SRC="$TMP/source.mp4"
IMG="$TMP/image.png"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=160x90:rate=30' -t 0.8 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$SRC"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x314765:size=160x90' -frames:v 1 -y "$IMG"

duration(){ "$FFPROBE" -v error -show_entries format=duration -of default=nw=1:nk=1 "$1"; }
check(){
  local file="$1" lo="$2" hi="$3" label="$4" d
  test -s "$file"
  d="$(duration "$file")"
  python3 - "$d" "$lo" "$hi" "$label" <<'PY'
import sys
v,lo,hi=float(sys.argv[1]),float(sys.argv[2]),float(sys.argv[3])
if not lo <= v <= hi:
    raise SystemExit(f"{sys.argv[4]} duration out of range: {v} not in [{lo},{hi}]")
PY
  "$FFMPEG" -hide_banner -loglevel error -i "$file" -frames:v 1 -f null - >/dev/null 2>&1
}

# 25 rounds × 4 modes = 100 independent FFmpeg smoke checks.
for n in $(seq 1 25); do
  IMAGE_OUT="$TMP/image-$n.mp4"
  ORIGINAL_OUT="$TMP/original-$n.mp4"
  PING_OUT="$TMP/pingpong-$n.mp4"
  CROSS_OUT="$TMP/crossfade-$n.mp4"

  "$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 30 -i "$IMG" -t 0.8 -an -vf 'scale=160:90,fps=30,setsar=1' -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$IMAGE_OUT"
  check "$IMAGE_OUT" 0.75 0.90 "Image#$n"

  "$FFMPEG" -hide_banner -loglevel error -i "$SRC" -t 0.8 -an -vf 'scale=160:90,fps=30,setsar=1' -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$ORIGINAL_OUT"
  check "$ORIGINAL_OUT" 0.75 0.90 "Original#$n"

  "$FFMPEG" -hide_banner -loglevel error -i "$SRC" -filter_complex '[0:v]trim=duration=0.8,setpts=PTS-STARTPTS,split[f][r];[r]reverse[rr];[f][rr]concat=n=2:v=1:a=0[x];[x]scale=160:90,fps=30,setsar=1[outv]' -map '[outv]' -t 1.6 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$PING_OUT"
  check "$PING_OUT" 1.50 1.70 "PingPong#$n"

  "$FFMPEG" -hide_banner -loglevel error -i "$SRC" -i "$SRC" -filter_complex '[0:v]trim=duration=0.8,setpts=PTS-STARTPTS,fps=30,settb=AVTB[a];[1:v]trim=duration=0.8,setpts=PTS-STARTPTS,fps=30,settb=AVTB[b];[a][b]xfade=transition=fade:duration=0.2:offset=0.6,trim=start=0.2:duration=0.8,setpts=PTS-STARTPTS[x];[x]scale=160:90,fps=30,setsar=1[outv]' -map '[outv]' -t 0.8 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$CROSS_OUT"
  check "$CROSS_OUT" 0.75 0.90 "Crossfade#$n"
done

echo 'ENDLUME loop modes: 100/100 smoke checks passed (Image, Crossfade, Ping-pong, Original).'
