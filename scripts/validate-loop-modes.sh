#!/bin/bash
set -euo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

SRC="$TMP/source.mp4"
IMG="$TMP/image.png"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=96x54:rate=20' -frames:v 6 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$SRC"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x314765:size=96x54' -frames:v 1 -y "$IMG"

check(){
  test -s "$1"
  "$FFPROBE" -v error -select_streams v:0 -show_entries stream=codec_type -of default=nw=1:nk=1 "$1" | grep -q video
}

round(){
  n="$1"
  IMAGE_OUT="$TMP/image-$n.mp4"
  ORIGINAL_OUT="$TMP/original-$n.mp4"
  PING_OUT="$TMP/pingpong-$n.mp4"
  CROSS_OUT="$TMP/crossfade-$n.mp4"

  "$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 20 -i "$IMG" -frames:v 6 -an -vf 'scale=96:54,fps=20,setsar=1' -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$IMAGE_OUT"
  check "$IMAGE_OUT"

  "$FFMPEG" -hide_banner -loglevel error -i "$SRC" -frames:v 6 -an -vf 'scale=96:54,fps=20,setsar=1' -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$ORIGINAL_OUT"
  check "$ORIGINAL_OUT"

  "$FFMPEG" -hide_banner -loglevel error -i "$SRC" -filter_complex '[0:v]trim=duration=0.3,setpts=PTS-STARTPTS,split[f][r];[r]reverse[rr];[f][rr]concat=n=2:v=1:a=0[x];[x]scale=96:54,fps=20,setsar=1[outv]' -map '[outv]' -frames:v 12 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$PING_OUT"
  check "$PING_OUT"

  "$FFMPEG" -hide_banner -loglevel error -i "$SRC" -i "$SRC" -filter_complex '[0:v]trim=duration=0.3,setpts=PTS-STARTPTS,fps=20,settb=AVTB[a];[1:v]trim=duration=0.3,setpts=PTS-STARTPTS,fps=20,settb=AVTB[b];[a][b]xfade=transition=fade:duration=0.05:offset=0.25,trim=start=0.05:duration=0.3,setpts=PTS-STARTPTS[x];[x]scale=96:54,fps=20,setsar=1[outv]' -map '[outv]' -frames:v 6 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$CROSS_OUT"
  check "$CROSS_OUT"
}

export -f check round
export FFMPEG FFPROBE TMP SRC IMG
pids=()
for n in {1..25}; do
  round "$n" &
  pids+=("$!")
  if (( n % 5 == 0 )); then
    for pid in "${pids[@]}"; do wait "$pid"; done
    pids=()
  fi
done

echo 'ENDLUME loop modes: 100/100 smoke checks passed (25 × Image, Crossfade, Ping-pong, Original).'
