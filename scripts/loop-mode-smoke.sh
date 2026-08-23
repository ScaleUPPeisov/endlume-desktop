#!/bin/bash
set -euo pipefail
FFMPEG="${FFMPEG:-$(command -v ffmpeg)}"
FFPROBE="${FFPROBE:-$(command -v ffprobe)}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=320x180:rate=30' -t 0.7 -an -c:v libx264 -preset ultrafast -crf 18 -pix_fmt yuv420p -y "$TMP/source.mp4"
"$FFMPEG" -hide_banner -loglevel error -i "$TMP/source.mp4" -frames:v 1 -y "$TMP/source.png"

verify(){
  local file="$1" min="$2"
  test -s "$file"
  local d
  d="$($FFPROBE -v error -show_entries format=duration -of default=nw=1:nk=1 "$file")"
  python3 - "$d" "$min" <<'PY'
import sys
actual=float(sys.argv[1]); minimum=float(sys.argv[2])
assert actual >= minimum, (actual, minimum)
PY
}

passes=0
for i in $(seq 1 25); do
  out="$TMP/image-$i.mp4"
  "$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 30 -i "$TMP/source.png" -vf 'scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1' -t 0.7 -an -c:v libx264 -preset ultrafast -crf 18 -pix_fmt yuv420p -y "$out"
  verify "$out" 0.60; passes=$((passes+1))
done

for i in $(seq 1 25); do
  out="$TMP/crossfade-$i.mp4"
  "$FFMPEG" -hide_banner -loglevel error -i "$TMP/source.mp4" -i "$TMP/source.mp4" -filter_complex '[0:v]trim=duration=0.7,setpts=PTS-STARTPTS[a];[1:v]trim=duration=0.7,setpts=PTS-STARTPTS[b];[a][b]xfade=transition=fade:duration=0.1:offset=0.6,trim=start=0.1:duration=0.7,setpts=PTS-STARTPTS[x];[x]scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1[outv]' -map '[outv]' -t 0.7 -an -c:v libx264 -preset ultrafast -crf 18 -pix_fmt yuv420p -y "$out"
  verify "$out" 0.60; passes=$((passes+1))
done

for i in $(seq 1 25); do
  out="$TMP/pingpong-$i.mp4"
  "$FFMPEG" -hide_banner -loglevel error -i "$TMP/source.mp4" -filter_complex '[0:v]trim=duration=0.7,setpts=PTS-STARTPTS,split[f][r];[r]reverse[rr];[f][rr]concat=n=2:v=1:a=0[x];[x]scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1[outv]' -map '[outv]' -t 1.4 -an -c:v libx264 -preset ultrafast -crf 18 -pix_fmt yuv420p -y "$out"
  verify "$out" 1.25; passes=$((passes+1))
done

for i in $(seq 1 25); do
  out="$TMP/original-$i.mp4"
  "$FFMPEG" -hide_banner -loglevel error -i "$TMP/source.mp4" -vf 'scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1' -t 0.7 -an -c:v libx264 -preset ultrafast -crf 18 -pix_fmt yuv420p -y "$out"
  verify "$out" 0.60; passes=$((passes+1))
done

test "$passes" -eq 100
echo "ENDLUME Loop Mode smoke: $passes/100 passed (Image 25, Crossfade 25, Ping-pong 25, Original 25)"
