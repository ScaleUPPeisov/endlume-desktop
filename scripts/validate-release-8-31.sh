#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
fail(){ echo "FAIL: $1"; exit 1; }
pass(){ echo "PASS: $1"; }

RUST="src-tauri/src/render.rs"
MODEL="src-tauri/src/model.rs"
PROJECT="src/pages/ProjectPage.tsx"
RENDER_UI="src/pages/RenderPage.tsx"
TYPES="src/types.ts"

# Static source gates.
grep -q 'build_lossless_processed_audio_cycle' "$RUST" || fail 'lossless processed-audio path missing'
grep -q 'acrossfade=d=' "$RUST" || fail 'real acrossfade filter missing'
grep -q 'audio-processed-lossless.m4a' "$RUST" || fail 'ALAC processed cycle missing'
grep -q '"-c:a","alac"' "$RUST" || fail 'ALAC encoder missing'
grep -q 'crossfadeApplied' "$RUST" || fail 'crossfade telemetry missing'
grep -q 'if s.noise1' "$RUST" || fail 'Noise 1 render filter missing'
grep -q 'if s.noise2' "$RUST" || fail 'Noise 2 render filter missing'
grep -q 'pub noise1:bool' "$MODEL" || fail 'Noise 1 Rust setting missing'
grep -q 'noise1?: boolean' "$TYPES" || fail 'Noise 1 TS setting missing'
grep -q 'ВСТРОЕННЫЕ ЭФФЕКТЫ' "$PROJECT" || fail 'built-in effects UI missing'
grep -q 'Шум 1' "$PROJECT" || fail 'Noise 1 UI missing'
grep -q 'Шум 2' "$PROJECT" || fail 'Noise 2 UI missing'
grep -q 'Переход реально сводится между песнями' "$PROJECT" || fail 'crossfade UI fix missing'
grep -q 'СЕЙЧАС ВЫПОЛНЯЕТСЯ' "$RENDER_UI" || fail 'live render stage UI missing'
grep -q 'const fallback=Math.max' "$RENDER_UI" || fail 'render stage fallback missing'
if grep -q '>ORIGINAL FIDELITY<' "$PROJECT"; then fail 'verbose ORIGINAL FIDELITY card still present'; fi
pass '8.31 static gates'

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# Real crossfade: two lossy sources -> processed result must be ALAC and duration
# must include the overlap (3s + 3s - 1s ≈ 5s).
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=440:sample_rate=44100' -t 3 -ac 2 -c:a libmp3lame -b:a 320k -y "$TMP/a.mp3"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=880:sample_rate=44100' -t 3 -ac 2 -c:a libmp3lame -b:a 320k -y "$TMP/b.mp3"
"$FFMPEG" -hide_banner -loglevel error -i "$TMP/a.mp3" -i "$TMP/b.mp3" -filter_complex '[0:a]aresample=48000,aformat=sample_fmts=s32p:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a0];[1:a]aresample=48000,aformat=sample_fmts=s32p:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a1];[a0][a1]acrossfade=d=1:c1=tri:c2=tri[outa]' -map '[outa]' -c:a alac -y "$TMP/crossfade.m4a"
CODEC="$("$FFPROBE" -v error -select_streams a:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$TMP/crossfade.m4a")"
[[ "$CODEC" == "alac" ]] || fail "crossfade output codec is $CODEC, expected alac"
DUR="$("$FFPROBE" -v error -show_entries format=duration -of default=nw=1:nk=1 "$TMP/crossfade.m4a")"
python3 - "$DUR" <<'PY'
import sys
x=float(sys.argv[1])
if not 4.7 <= x <= 5.3:
    raise SystemExit(f'crossfade duration invalid: {x}')
PY
"$FFMPEG" -hide_banner -loglevel error -i "$TMP/crossfade.m4a" -map 0:a:0 -t 0.5 -f null -
pass 'real 1-second crossfade -> decodable ALAC lossless output'

# Both built-in noise filters must be valid in the bundled FFmpeg syntax.
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x182038:size=640x360:rate=30' -vf 'noise=alls=4:allf=u' -t 0.5 -f null -
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x182038:size=640x360:rate=30' -vf 'noise=alls=7:allf=u' -t 0.5 -f null -
pass 'Noise 1/2 FFmpeg filters execute'

echo 'ENDLUME 8.31 runtime UX/crossfade/noise gate passed.'