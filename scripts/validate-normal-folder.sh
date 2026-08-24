#!/usr/bin/env bash
set -euo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/Новая папка"
DIR="$TMP/Новая папка"

# Match the user's real failure class: one PNG + Unicode/French MP3 names,
# mixed sample rates and channel layouts.
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i "color=c=0x15182a:s=1280x720:r=60" -frames:v 1 -y "$DIR/ChatGPT Image 27 июня — тест.png"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i "sine=frequency=440:duration=2:sample_rate=44100" -ac 1 -c:a libmp3lame -b:a 192k -y "$DIR/Après l’amour.mp3"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i "sine=frequency=550:duration=2:sample_rate=48000" -ac 2 -c:a libmp3lame -b:a 256k -y "$DIR/“Neon Wet Rose”.mp3"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i "sine=frequency=660:duration=2:sample_rate=32000" -ac 2 -c:a libmp3lame -b:a 160k -y "$DIR/Absence Sous-Pluie.mp3"

"$FFMPEG" -hide_banner -loglevel error \
  -i "$DIR/Après l’amour.mp3" -i "$DIR/“Neon Wet Rose”.mp3" -i "$DIR/Absence Sous-Pluie.mp3" \
  -filter_complex "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,aresample=48000,asetpts=N/SR/TB[a0];[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,aresample=48000,asetpts=N/SR/TB[a1];[2:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,aresample=48000,asetpts=N/SR/TB[a2];[a0][a1]acrossfade=d=0.4:c1=tri:c2=tri[x1];[x1][a2]acrossfade=d=0.4:c1=tri:c2=tri[outa]" \
  -map "[outa]" -c:a aac -b:a 320k -ar 48000 -ac 2 -y "$TMP/audio-cycle.m4a"

"$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 60 -i "$DIR/ChatGPT Image 27 июня — тест.png" -t 2 -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=60,format=yuv420p" -c:v libx264 -preset ultrafast -crf 18 -an -y "$TMP/video.mp4"
"$FFMPEG" -hide_banner -loglevel error -i "$TMP/video.mp4" -i "$TMP/audio-cycle.m4a" -t 2 -map 0:v:0 -map 1:a:0 -c:v copy -c:a copy -y "$TMP/final.mp4"

test -s "$TMP/final.mp4"
DUR="$($FFPROBE -v error -show_entries format=duration -of default=nw=1:nk=1 "$TMP/final.mp4")"
python3 - "$DUR" <<'PY'
import sys
assert float(sys.argv[1]) > 1.5
PY

echo "Verified normal folder regression: Unicode paths + mixed MP3 formats + final mux"
