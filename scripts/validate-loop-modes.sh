#!/bin/bash
set -euo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

SRC="$TMP/source.mp4"
IMG="$TMP/ChatGPT Image 27 июн. 2026 г., 23_38_49.png"
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

# Regression matching an ordinary user folder: Unicode/French filenames + mixed MP3 sample rates/layouts.
A0="$TMP/__Quais, minuit humide__.mp3"
A1="$TMP/“Neon Wet Rose”.mp3"
A2="$TMP/Après l’amour.mp3"
A3="$TMP/Autoroute Lavender.mp3"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=310:duration=0.8:sample_rate=44100' -ac 1 -c:a libmp3lame -b:a 128k -y "$A0"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=420:duration=0.8:sample_rate=48000' -ac 2 -c:a libmp3lame -b:a 192k -y "$A1"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=530:duration=0.8:sample_rate=32000' -ac 1 -c:a libmp3lame -b:a 160k -y "$A2"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=640:duration=0.8:sample_rate=44100' -ac 2 -c:a libmp3lame -b:a 224k -y "$A3"
AUDIO_OUT="$TMP/normal-project-audio.m4a"
"$FFMPEG" -hide_banner -loglevel error -i "$A0" -i "$A1" -i "$A2" -i "$A3" -filter_complex '[0:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a0];[1:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a1];[2:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a2];[3:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a3];[a0][a1]acrossfade=d=0.10:c1=tri:c2=tri[x1];[x1][a2]acrossfade=d=0.10:c1=tri:c2=tri[x2];[x2][a3]acrossfade=d=0.10:c1=tri:c2=tri[x3];[x3]alimiter=limit=0.97[outa]' -map '[outa]' -c:a aac -b:a 320k -ar 48000 -ac 2 -y "$AUDIO_OUT"
test -s "$AUDIO_OUT"
"$FFPROBE" -v error -select_streams a:0 -show_entries stream=sample_rate,channels -of csv=p=0 "$AUDIO_OUT" | grep -q '48000,2'

NORMAL_OUT="$TMP/Новая папка — Ready Videos.mp4"
"$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 30 -i "$IMG" -i "$AUDIO_OUT" -t 2.0 -map 0:v:0 -map 1:a:0 -vf 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1' -c:v libx264 -preset ultrafast -tune stillimage -crf 18 -pix_fmt yuv420p -c:a copy -movflags +faststart -y "$NORMAL_OUT"
test -s "$NORMAL_OUT"
"$FFPROBE" -v error -select_streams v:0 -show_entries stream=codec_type -of default=nw=1:nk=1 "$NORMAL_OUT" | grep -q video
"$FFPROBE" -v error -select_streams a:0 -show_entries stream=codec_type -of default=nw=1:nk=1 "$NORMAL_OUT" | grep -q audio

# Chromakey fidelity: green background becomes alpha, visible red subject remains a valid overlay.
KEY_SRC="$TMP/chroma-source.mp4"
KEY_CACHE="$TMP/chroma-cache.mov"
KEY_FINAL="$TMP/chroma-final.mp4"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x00ff00:size=320x180:rate=30,drawbox=x=70:y=35:w=180:h=110:color=0xff3355:t=fill' -t 1 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$KEY_SRC"
"$FFMPEG" -hide_banner -loglevel error -i "$KEY_SRC" -vf 'fps=30,format=rgba,colorkey=0x00ff00:0.10:0.06,format=argb' -an -c:v qtrle -pix_fmt argb -y "$KEY_CACHE"
check "$KEY_CACHE"
"$FFMPEG" -hide_banner -loglevel error -loop 1 -i "$IMG" -stream_loop -1 -i "$KEY_CACHE" -filter_complex '[0:v]scale=640:360,fps=30,setsar=1[b];[1:v]scale=320:180[fx];[b][fx]overlay=x=160:y=90:shortest=1[outv]' -map '[outv]' -t 1 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$KEY_FINAL"
check "$KEY_FINAL"

grep -Fq 'job.effects.iter().filter(|e|e.enabled)' src-tauri/src/render.rs
grep -Fq 'job.subscribes.iter().filter(|s|s.effect.enabled)' src-tauri/src/render.rs
grep -Fq 'match cache::prepare(app,e,job.settings.fps).await' src-tauri/src/render.rs
grep -Fq 'match cache::prepare(app,&s.effect,job.settings.fps).await' src-tauri/src/render.rs
grep -Fq 'refresh_project_paths(&mut resolved_job)' src-tauri/src/render.rs
grep -Fq 'colorkey={}:{}:{}' src-tauri/src/render.rs
grep -Fq 'attempt==1{choose_encoder' src-tauri/src/render.rs
grep -Fq 'effects-v3-fidelity' src-tauri/src/cache.rs
grep -Fq 'colorkey=' src-tauri/src/cache.rs

echo 'ENDLUME regressions passed: normal folder + audio normalization + stale paths + overlay isolation + RGB colorkey fidelity + software encoder retry.'
