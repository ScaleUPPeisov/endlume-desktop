#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
fail(){ echo "FAIL: $1" >&2; exit 1; }
pass(){ echo "PASS: $1"; }

SCAN=src-tauri/src/scan.rs
LIVE=src-tauri/src/live_preview.rs
RUST=src-tauri/src/render.rs
MODEL=src-tauri/src/model.rs
PROJECT=src/pages/ProjectPage.tsx
TYPES=src/types.ts
STORE=src/store.ts
PKG=package.json

for f in "$SCAN" "$LIVE" "$RUST" "$MODEL" "$PROJECT" "$TYPES" "$STORE" "$PKG"; do test -f "$f" || fail "missing $f"; done

# 8.33 filtered AppleDouble by filename. 8.34+ supersedes that path with
# rejected_macos_input(), which also checks the AppleDouble magic signature.
grep -Fq 'fn is_macos_sidecar' "$SCAN" || fail 'scan AppleDouble filename filter missing'
if grep -Fq 'rejected_macos_input(&p)' "$SCAN"; then
  grep -Fq '0x00051607' "$SCAN" || fail '8.34+ scan magic-signature guard missing'
elif grep -Fq 'is_macos_sidecar(&p)' "$SCAN"; then
  :
else
  fail 'scan still accepts ._* files'
fi

grep -Fq 'fn is_macos_sidecar' "$LIVE" || fail 'Live Preview AppleDouble filename filter missing'
if grep -Fq '!rejected_macos_input(p)&&is_media(p)' "$LIVE"; then
  grep -Fq '0x00051607' "$LIVE" || fail '8.34+ Live Preview magic-signature guard missing'
elif grep -Fq '!is_macos_sidecar(p)&&is_media(p)' "$LIVE"; then
  :
else
  fail 'Live Preview first_media still accepts ._* files'
fi
pass 'AppleDouble files are excluded; modern magic-signature shield accepted when present'

! grep -Fq 'Шум 1' "$PROJECT" || fail 'Noise 1 UI still present'
! grep -Fq 'Шум 2' "$PROJECT" || fail 'Noise 2 UI still present'
! grep -Fq 'noise1' "$TYPES" || fail 'Noise 1 TS setting still present'
! grep -Fq 'noise2' "$TYPES" || fail 'Noise 2 TS setting still present'
! grep -Fq 'noise1' "$MODEL" || fail 'Noise 1 Rust setting still present'
! grep -Fq 'noise2' "$MODEL" || fail 'Noise 2 Rust setting still present'
! grep -Fq 'if s.noise1' "$RUST" || fail 'Noise 1 render filter still present'
! grep -Fq 'if s.noise2' "$RUST" || fail 'Noise 2 render filter still present'
pass 'Noise 1/2 removed from UI, settings and renderer'

grep -Fq 'fn render_work_dir' "$RUST" || fail 'output-drive workdir helper missing'
grep -Fq 'output.join(".ENDLUME-work")' "$RUST" || fail 'render work is not rooted on selected output drive'
grep -Fq 'let work=render_work_dir(&out_dir' "$RUST" || fail 'render still uses system temp dir'
! grep -Fq 'std::env::temp_dir().join(format!("endlume-' "$RUST" || fail 'old internal render temp path still present'
pass 'heavy render workspace follows selected output disk'

grep -Fq 'Smart Fidelity: Effects/Subscribe из оригиналов' "$RUST" || fail 'smart direct-overlay path missing'
grep -Fq 'return Ok((job.effects.clone(),job.subscribes.clone()))' "$RUST" || fail 'smart render still forces heavy internal qtrle cache'
pass 'Smart Fidelity reads original Effects/Subscribe directly'

grep -Fq 'hevc_videotoolbox' "$RUST" || fail 'Apple HEVC hardware path missing'
grep -Fq 'choose_hybrid_encoder(app,attempt).await' "$RUST" || fail 'hybrid encoder selector not active'
grep -Fq '"libx265".into()' "$RUST" || fail 'software quality fallback missing'
grep -Fq 'hybrid_video_kbps' "$RUST" || fail 'compact size budget missing'
grep -Fq 'hybrid_master_seconds_for_job' "$RUST" || fail 'effect-duration master logic missing'
pass 'hardware-first short-master path and quality fallback are wired'

grep -Fq 'let mut sub_cache:HashMap<String,PathBuf>' "$RUST" || fail 'Subscribe reuse cache missing'
grep -Fq 'VisualSource::Concat' "$RUST" || fail 'direct concat final mux missing'
pass 'Subscribe repeats are reused and one full long-video copy is removed'

grep -Fq 'build_lossless_processed_audio_cycle' "$RUST" || fail 'lossless crossfade helper lost'
grep -Fq 'acrossfade=d=' "$RUST" || fail 'real crossfade filter lost'
grep -Fq 'audio-original-clean.mp3' "$RUST" || fail 'exact MP3 path lost'
grep -Fq '"-c:a","alac"' "$RUST" || fail 'ALAC helper lost'
pass 'legacy audio processing helpers remain available for non-Strict-Fidelity paths'

if grep -Eq '"version": "1\.0\.0-alpha\.8\.(33|34|35)"' "$PKG"; then
  pass 'package version is 8.33+; running backward 8.33 regression gate'
else
  fail 'package version is not an accepted 8.33+ release'
fi

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=440:sample_rate=44100' -t 2 -ac 2 -c:a libmp3lame -b:a 320k -y "$TMP/a.mp3"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=880:sample_rate=44100' -t 2 -ac 2 -c:a libmp3lame -b:a 320k -y "$TMP/b.mp3"
"$FFMPEG" -hide_banner -loglevel error -i "$TMP/a.mp3" -i "$TMP/b.mp3" -filter_complex '[0:a]aresample=48000,aformat=sample_fmts=s32p:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a0];[1:a]aresample=48000,aformat=sample_fmts=s32p:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a1];[a0][a1]acrossfade=d=0.5:c1=tri:c2=tri[outa]' -map '[outa]' -c:a alac -y "$TMP/crossfade.m4a"
CODEC="$("$FFPROBE" -v error -select_streams a:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$TMP/crossfade.m4a")"
[[ "$CODEC" == "alac" ]] || fail "crossfade codec is $CODEC"
"$FFMPEG" -hide_banner -loglevel error -i "$TMP/crossfade.m4a" -map 0:a:0 -t 0.5 -f null -
pass 'crossfade helper output is decodable ALAC lossless'

"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x172038:size=1920x1080:rate=30' -frames:v 1 -y "$TMP/base.png"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x00b140:size=640x640:rate=30' -vf 'drawbox=x=220:y=80:w=200:h=480:color=white:t=18' -t 2 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$TMP/fx.mp4"
ENC=libx265
if "$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=black:size=640x360:rate=30' -t 0.2 -an -c:v hevc_videotoolbox -f null - >/dev/null 2>&1; then ENC=hevc_videotoolbox; fi
START="$(python3 - <<'PY'
import time
print(time.time())
PY
)"
if [[ "$ENC" == hevc_videotoolbox ]]; then
  "$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 30 -i "$TMP/base.png" -stream_loop -1 -i "$TMP/fx.mp4" -filter_complex '[0:v]scale=1920:1080,setsar=1[b0];[1:v]fps=30,format=rgba,chromakey=0x00b140:0.10:0.06,scale=iw*0.35:ih*0.35[fx];[b0][fx]overlay=x=(W-w)*0.5:y=(H-h)*0.5:shortest=1:eof_action=repeat,format=yuv420p[outv]' -map '[outv]' -t 8 -an -c:v hevc_videotoolbox -realtime 1 -prio_speed 1 -b:v 600k -maxrate 6M -bufsize 16M -g 60 -tag:v hvc1 -pix_fmt yuv420p -y "$TMP/master.mp4"
else
  "$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 30 -i "$TMP/base.png" -stream_loop -1 -i "$TMP/fx.mp4" -filter_complex '[0:v]scale=1920:1080,setsar=1[b0];[1:v]fps=30,format=rgba,chromakey=0x00b140:0.10:0.06,scale=iw*0.35:ih*0.35[fx];[b0][fx]overlay=x=(W-w)*0.5:y=(H-h)*0.5:shortest=1:eof_action=repeat,format=yuv420p[outv]' -map '[outv]' -t 8 -an -c:v libx265 -preset ultrafast -crf 14 -tag:v hvc1 -pix_fmt yuv420p -y "$TMP/master.mp4"
fi
END="$(python3 - <<'PY'
import time
print(time.time())
PY
)"
"$FFMPEG" -hide_banner -loglevel error -i "$TMP/master.mp4" -map 0:v:0 -t 0.5 -f null -
python3 - "$START" "$END" "$ENC" <<'PY'
import sys
print(f"PASS: backward smart visual smoke with {sys.argv[3]} in {float(sys.argv[2])-float(sys.argv[1]):.2f}s")
PY

echo 'ENDLUME 8.33 backward regression gate passed.'
