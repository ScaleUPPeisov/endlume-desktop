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

# 8.33 filtered AppleDouble by filename. 8.34 supersedes that path with
# rejected_macos_input(), which also checks the AppleDouble magic signature.
grep -Fq 'fn is_macos_sidecar' "$SCAN" || fail 'scan AppleDouble filename filter missing'
if grep -Fq 'rejected_macos_input(&p)' "$SCAN"; then
  grep -Fq '0x00051607' "$SCAN" || fail '8.34 scan magic-signature guard missing'
elif grep -Fq 'is_macos_sidecar(&p)' "$SCAN"; then
  :
else
  fail 'scan still accepts ._* files'
fi

grep -Fq 'fn is_macos_sidecar' "$LIVE" || fail 'Live Preview AppleDouble filename filter missing'
if grep -Fq '!rejected_macos_input(p)&&is_media(p)' "$LIVE"; then
  grep -Fq '0x00051607' "$LIVE" || fail '8.34 Live Preview magic-signature guard missing'
elif grep -Fq '!is_macos_sidecar(p)&&is_media(p)' "$LIVE"; then
  :
else
  fail 'Live Preview first_media still accepts ._* files'
fi
pass 'AppleDouble files are excluded; 8.34 magic-signature shield accepted when present'

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

grep -Fq 'build_lossless_processed_audio_cycle' "$RUST" || fail 'lossless crossfade path lost'
grep -Fq 'acrossfade=d=' "$RUST" || fail 'real crossfade filter lost'
grep -Fq 'audio-original-clean.mp3' "$RUST" || fail 'exact MP3 path lost'
grep -Fq '"-c:a","alac"' "$RUST" || fail 'ALAC lossless fallback lost'
pass 'audio fidelity and real crossfade paths remain present'

# This regression gate may run after 8.34 hardening has already bumped the
# package version. Accept both the native 8.33 stage and the superseding 8.34.
if grep -Fq '"version": "1.0.0-alpha.8.33"' "$PKG"; then
  pass 'package version is 8.33 for native regression stage'
elif grep -Fq '"version": "1.0.0-alpha.8.34"' "$PKG"; then
  pass 'package version is 8.34; running backward 8.33 regression gate after hardening'
else
  fail 'package version is neither 8.33 nor 8.34'
fi

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# Real audio regression: two MP3 inputs crossfade into lossless ALAC.
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=440:sample_rate=44100' -t 2 -ac 2 -c:a libmp3lame -b:a 320k -y "$TMP/a.mp3"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=880:sample_rate=44100' -t 2 -ac 2 -c:a libmp3lame -b:a 320k -y "$TMP/b.mp3"
"$FFMPEG" -hide_banner -loglevel error -i "$TMP/a.mp3" -i "$TMP/b.mp3" -filter_complex '[0:a]aresample=48000,aformat=sample_fmts=s32p:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a0];[1:a]aresample=48000,aformat=sample_fmts=s32p:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a1];[a0][a1]acrossfade=d=0.5:c1=tri:c2=tri[outa]' -map '[outa]' -c:a alac -y "$TMP/crossfade.m4a"
CODEC="$("$FFPROBE" -v error -select_streams a:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$TMP/crossfade.m4a")"
[[ "$CODEC" == "alac" ]] || fail "crossfade codec is $CODEC"
"$FFMPEG" -hide_banner -loglevel error -i "$TMP/crossfade.m4a" -map 0:a:0 -t 0.5 -f null -
pass 'crossfade output is decodable ALAC lossless'

# Real smart visual smoke. Prefer VideoToolbox on Apple Silicon; validate the
# same filter graph with x265 fallback everywhere else.
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
print(f"PASS: smart visual master encoded with {sys.argv[3]} in {float(sys.argv[2])-float(sys.argv[1]):.2f}s")
PY

# Size-budget math: 2h HEVC target + exact 320k MP3 should sit around 1 GB.
python3 - <<'PY'
for video in (600,680,760):
    total=(video+320)*1000*7200/8
    if not 0.80e9 <= total <= 1.05e9:
        raise SystemExit(f'FAIL: 2h size budget out of range: {video}k -> {total/1e9:.3f} GB')
    print(f'PASS: 2h budget {video}k video + 320k audio -> {total/1e9:.3f} GB')
PY

echo 'ENDLUME 8.33 SSD + Fast Fidelity + Effects/Subscribe regression gate passed.'
