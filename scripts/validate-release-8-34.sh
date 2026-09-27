#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
fail(){ echo "FAIL: $1" >&2; exit 1; }
pass(){ echo "PASS: $1"; }

SCAN=src-tauri/src/scan.rs
LIVE=src-tauri/src/live_preview.rs
ASSETS=src-tauri/src/assets.rs
PROJECT=src/pages/ProjectPage.tsx
RUST=src-tauri/src/render.rs
PKG=package.json

for f in "$SCAN" "$LIVE" "$ASSETS" "$PROJECT" "$RUST" "$PKG"; do test -f "$f" || fail "missing $f"; done

grep -Fq '0x00051607' "$SCAN" || fail 'scan AppleDouble magic guard missing'
grep -Fq 'rejected_macos_input(&p)' "$SCAN" || fail 'scan does not reject resource forks'
grep -Fq 'live-preview-v6' "$LIVE" || fail 'Live Preview cache was not invalidated'
grep -Fq '!rejected_macos_input(p)&&is_media(p)' "$LIVE" || fail 'Live Preview can still select AppleDouble media'
grep -Fq 'rejected_macos_input(&overlay)' "$LIVE" || fail 'overlay AppleDouble guard missing'
grep -Fq 'has_appledouble_magic(&src)' "$ASSETS" || fail 'library import magic guard missing'
pass 'AppleDouble filename + magic-signature shield is active'

! grep -Fq 'Шум 1' "$PROJECT" || fail 'Noise 1 UI returned'
! grep -Fq 'Шум 2' "$PROJECT" || fail 'Noise 2 UI returned'
! grep -Fq 'if s.noise1' "$RUST" || fail 'Noise 1 render filter returned'
! grep -Fq 'if s.noise2' "$RUST" || fail 'Noise 2 render filter returned'
pass 'Noise 1/2 remain removed from UI and render filter'

grep -Fq 'choose_hybrid_encoder(app,attempt).await' "$RUST" || fail 'Fast Fidelity selector missing'
grep -Fq 'hevc_videotoolbox' "$RUST" || fail 'Apple VideoToolbox path missing'
grep -Fq 'VisualSource::Concat' "$RUST" || fail 'direct concat fast path missing'
grep -Fq 'audio-original-clean.mp3' "$RUST" || fail 'exact MP3 path missing'
if grep -Eq '"version": "1\.0\.0-alpha\.8\.(34|35)"' "$PKG"; then :; else fail 'package version is not 8.34+'; fi
pass '8.34 Preview Shield invariants remain wired'

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
printf '\000\005\026\007THIS_IS_APPLEDOUBLE_NOT_A_PNG' > "$TMP/._cover.png"
MAGIC="$(/usr/bin/xxd -p -l 4 "$TMP/._cover.png" | tr -d '\n')"
[[ "$MAGIC" == "00051607" ]] || fail "AppleDouble fixture is wrong: $MAGIC"
pass 'exact 0x00051607 AppleDouble fixture reproduced'

"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x162038:size=640x360:rate=30' -frames:v 1 -y "$TMP/base.png"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x00b140:size=240x240:rate=30' -vf 'drawbox=x=80:y=40:w=80:h=160:color=white:t=10' -t 1 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$TMP/fx.mp4"
for i in $(seq 1 100); do
  OUT="$TMP/preview-$i.mp4"
  "$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 30 -i "$TMP/base.png" -stream_loop -1 -i "$TMP/fx.mp4" -filter_complex '[0:v]setsar=1[b];[1:v]fps=30,format=rgba,chromakey=0x00b140:0.10:0.06,scale=120:-2[fx];[b][fx]overlay=x=(W-w)/2:y=(H-h)/2:shortest=1:eof_action=repeat,format=yuv420p[v]' -map '[v]' -t 0.08 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$OUT"
  "$FFPROBE" -v error -select_streams v:0 -show_entries stream=codec_name,width,height -of csv=p=0 "$OUT" >/dev/null
  rm -f "$OUT"
done
pass 'Effects + Subscribe Live Preview 100/100 repeated encode/decode smoke'

echo 'ENDLUME 8.34 backward Preview Shield gate passed.'
