#!/bin/bash
set -euo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

check_video(){ test -s "$1"; "$FFPROBE" -v error -select_streams v:0 -show_entries stream=codec_type -of default=nw=1:nk=1 "$1" | grep -q video; }
check_audio(){ "$FFPROBE" -v error -select_streams a:0 -show_entries stream=codec_type -of default=nw=1:nk=1 "$1" | grep -q audio; }
assert_contains(){ local needle="$1" file="$2" label="$3"; grep -Fq "$needle" "$file" || { echo "FAIL: $label"; echo "Expected: $needle"; exit 1; }; echo "PASS: $label"; }

IMG="$TMP/base.png"
SRC="$TMP/source.mp4"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x314765:size=320x180' -frames:v 1 -y "$IMG"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=320x180:rate=30' -t 0.5 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$SRC"

for n in {1..25}; do
  "$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 30 -i "$IMG" -frames:v 6 -an -vf 'scale=320:180,fps=30,setsar=1' -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$TMP/image-$n.mp4"
  check_video "$TMP/image-$n.mp4"
  "$FFMPEG" -hide_banner -loglevel error -i "$SRC" -frames:v 6 -an -vf 'scale=320:180,fps=30,setsar=1' -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$TMP/original-$n.mp4"
  check_video "$TMP/original-$n.mp4"
  "$FFMPEG" -hide_banner -loglevel error -i "$SRC" -filter_complex '[0:v]trim=duration=0.3,setpts=PTS-STARTPTS,split[f][r];[r]reverse[rr];[f][rr]concat=n=2:v=1:a=0[x];[x]scale=320:180,fps=30,setsar=1[outv]' -map '[outv]' -frames:v 12 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$TMP/ping-$n.mp4"
  check_video "$TMP/ping-$n.mp4"
  "$FFMPEG" -hide_banner -loglevel error -i "$SRC" -i "$SRC" -filter_complex '[0:v]trim=duration=0.3,setpts=PTS-STARTPTS,fps=30,settb=AVTB[a];[1:v]trim=duration=0.3,setpts=PTS-STARTPTS,fps=30,settb=AVTB[b];[a][b]xfade=transition=fade:duration=0.05:offset=0.25,trim=start=0.05:duration=0.3,setpts=PTS-STARTPTS[x];[x]scale=320:180,fps=30,setsar=1[outv]' -map '[outv]' -frames:v 6 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$TMP/cross-$n.mp4"
  check_video "$TMP/cross-$n.mp4"
done
echo 'PASS: Loop Mode 100/100'

A0="$TMP/Après l’amour.mp3"
A1="$TMP/Neon Wet Rose.mp3"
A2="$TMP/Quais minuit humide.mp3"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=310:duration=0.8:sample_rate=44100' -ac 1 -c:a libmp3lame -b:a 128k -y "$A0"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=420:duration=0.8:sample_rate=48000' -ac 2 -c:a libmp3lame -b:a 192k -y "$A1"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=530:duration=0.8:sample_rate=32000' -ac 1 -c:a libmp3lame -b:a 160k -y "$A2"
AUDIO="$TMP/audio.m4a"
"$FFMPEG" -hide_banner -loglevel error -i "$A0" -i "$A1" -i "$A2" -filter_complex '[0:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a0];[1:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a1];[2:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a2];[a0][a1]acrossfade=d=0.10:c1=tri:c2=tri[x1];[x1][a2]acrossfade=d=0.10:c1=tri:c2=tri[outa]' -map '[outa]' -c:a aac -b:a 320k -ar 48000 -ac 2 -y "$AUDIO"
test -s "$AUDIO"
"$FFPROBE" -v error -select_streams a:0 -show_entries stream=sample_rate,channels -of csv=p=0 "$AUDIO" | grep -q '48000,2'
echo 'PASS: mixed MP3 normalization'

FXSRC="$TMP/effect-square.mp4"
FXCACHE="$TMP/effect-cache.mov"
SUBSRC="$TMP/subscribe-square.mp4"
SUBCACHE="$TMP/subscribe-cache.mov"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x00ff00:size=180x180:rate=30,drawbox=x=40:y=40:w=100:h=100:color=0xff3355:t=fill' -t 1 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$FXSRC"
"$FFMPEG" -hide_banner -loglevel error -i "$FXSRC" -vf 'fps=30,format=rgba,colorkey=0x00ff00:0.10:0.06,format=argb' -an -c:v qtrle -pix_fmt argb -y "$FXCACHE"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x00ff00:size=240x120:rate=30,drawbox=x=25:y=25:w=190:h=70:color=white:t=fill' -t 1 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$SUBSRC"
"$FFMPEG" -hide_banner -loglevel error -i "$SUBSRC" -vf 'fps=30,format=rgba,colorkey=0x00ff00:0.10:0.06,format=argb' -an -c:v qtrle -pix_fmt argb -y "$SUBCACHE"
FXDIM="$($FFPROBE -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "$FXCACHE")"
SUBDIM="$($FFPROBE -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "$SUBCACHE")"
[[ "$FXDIM" == "180x180" ]] || { echo "FAIL: effect aspect changed: $FXDIM"; exit 1; }
[[ "$SUBDIM" == "240x120" ]] || { echo "FAIL: subscribe aspect changed: $SUBDIM"; exit 1; }
COMPOSITE="$TMP/composite.mp4"
"$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 30 -i "$IMG" -stream_loop -1 -i "$FXCACHE" -stream_loop -1 -i "$SUBCACHE" -filter_complex '[0:v]scale=640:360,fps=30,setsar=1[b0];[1:v]scale=220:-2:flags=lanczos[fx];[b0][fx]overlay=x=max(0,min(W-w,W*0.5-w/2)):y=max(0,min(H-h,H*0.5-h/2)):shortest=1:eof_action=repeat[b1];[2:v]scale=180:-2:flags=lanczos[sub];[b1][sub]overlay=x=max(0,min(W-w,W*0.5-w/2)):y=max(0,min(H-h,H*0.82-h/2)):shortest=1:eof_action=repeat[outv]' -map '[outv]' -t 1 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$COMPOSITE"
check_video "$COMPOSITE"
echo 'PASS: Effects + Subscribe aspect-safe composition'

FINAL="$TMP/final.mp4"
"$FFMPEG" -hide_banner -loglevel error -stream_loop -1 -i "$COMPOSITE" -stream_loop -1 -i "$AUDIO" -t 2 -map 0:v:0 -map 1:a:0 -c:v copy -c:a copy -movflags +faststart -y "$FINAL"
check_video "$FINAL"; check_audio "$FINAL"
echo 'PASS: final mux video+audio'

assert_contains 'fn render_work_dir(' src-tauri/src/render.rs 'writable app-cache render workspace'
assert_contains 'refresh_project_paths(&mut resolved_job)' src-tauri/src/render.rs 'stale project paths recovery'
assert_contains 'resolve_output_dir(app,&requested_out_dir)' src-tauri/src/render.rs 'output permission fallback'
assert_contains 'software_encoder(&job.settings)' src-tauri/src/render.rs 'real software encoder retry'
assert_contains 'Effect '\''{}'\'' пропущен' src-tauri/src/render.rs 'broken Effect does not kill render'
assert_contains 'Subscribe '\''{}'\'' пропущен' src-tauri/src/render.rs 'broken Subscribe does not kill render'
assert_contains 'scale={}:-2:flags=lanczos' src-tauri/src/render.rs 'render keeps overlay aspect'
assert_contains 'aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo' src-tauri/src/render.rs 'audio normalized before crossfade'
assert_contains "chooseVideo('subscribe')" src/pages/Editors.tsx 'Subscribe imports into managed subscribe library'
assert_contains 'x: 0.5' src/pages/Editors.tsx 'new overlays auto-center'
assert_contains '"build": "tsc && vite build"' package.json 'build no longer mutates source files'

echo 'ENDLUME 8.25 regression gate passed.'
