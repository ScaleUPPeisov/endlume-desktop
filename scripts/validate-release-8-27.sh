#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass(){ echo "PASS: $1"; }
fail(){ echo "FAIL: $1" >&2; exit 1; }
contains(){ grep -Fq "$1" "$2" || fail "$3"; pass "$3"; }

contains 'fn fidelity_video_args(' src-tauri/src/render.rs 'Original Fidelity video encoder exists'
contains 'choose_fidelity_encoder(app,attempt).await' src-tauri/src/render.rs 'Apple Silicon fidelity encoder selection exists'
contains 'build_original_audio_cycle(' src-tauri/src/render.rs 'exact MP3 audio path exists'
contains 'Original Audio: копирую MP3 без перекодирования' src-tauri/src/render.rs 'exact audio stream-copy stage exists'
contains '"-c:a","alac"' src-tauri/src/render.rs 'ALAC lossless fallback exists'
contains '"originalFidelity":smart_repeat' src-tauri/src/render.rs 'Render Center receives fidelity profile'
contains 'audioOriginal' src/types.ts 'frontend receives original-audio telemetry'
contains 'ORIGINAL FIDELITY' src/pages/ProjectPage.tsx 'Project page explains fidelity mode'
contains 'Original Fidelity: quality-first HEVC' src/pages/RenderPage.tsx 'Render result shows actual fidelity mode'
contains 'qtrle' src-tauri/src/cache.rs 'Effects chromakey cache remains lossless qtrle'
if grep -Fq 'args.extend(static_smart_encoder_args(s));' src-tauri/src/render.rs; then fail 'old forced low-bitrate Smart Size call still active'; else pass 'forced low-bitrate Smart Size call removed from fidelity path'; fi

A="$TMP/a.mp3"; B="$TMP/b.mp3"; LIST="$TMP/list.ffconcat"; CYCLE="$TMP/cycle.mp3"; VID="$TMP/video.mp4"; FINAL="$TMP/final.mp4"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=440:sample_rate=44100' -t 1 -ac 2 -c:a libmp3lame -b:a 192k -y "$A"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=880:sample_rate=44100' -t 1 -ac 2 -c:a libmp3lame -b:a 192k -y "$B"
printf "ffconcat version 1.0\nfile '%s'\nfile '%s'\n" "$A" "$B" > "$LIST"
"$FFMPEG" -hide_banner -loglevel error -f concat -safe 0 -i "$LIST" -map 0:a:0 -c:a copy -fflags +genpts -avoid_negative_ts make_zero -y "$CYCLE"
CODEC="$($FFPROBE -v error -select_streams a:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$CYCLE")"
[[ "$CODEC" == "mp3" ]] || fail "exact audio cycle codec is $CODEC, expected mp3"
pass 'MP3 cycle stays MP3 via stream-copy'
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=black:size=640x360:rate=30' -t 2 -an -c:v libx264 -preset ultrafast -pix_fmt yuv420p -y "$VID"
"$FFMPEG" -hide_banner -loglevel error -stream_loop -1 -i "$VID" -stream_loop -1 -i "$CYCLE" -t 2 -map 0:v:0 -map 1:a:0 -c:v copy -c:a copy -movflags +faststart -y "$FINAL"
FINAL_AUDIO="$($FFPROBE -v error -select_streams a:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$FINAL")"
[[ "$FINAL_AUDIO" == "mp3" ]] || fail "final MP4 audio codec is $FINAL_AUDIO, expected mp3"
pass 'final MP4 keeps MP3 without re-encode'

M1="$TMP/m1.mp3"; M2="$TMP/m2.mp3"; LOSSLESS="$TMP/lossless.m4a"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=330:sample_rate=44100' -t 1 -ac 2 -c:a libmp3lame -b:a 192k -y "$M1"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=660:sample_rate=48000' -t 1 -ac 2 -c:a libmp3lame -b:a 192k -y "$M2"
"$FFMPEG" -hide_banner -loglevel error -i "$M1" -i "$M2" -filter_complex '[0:a]aresample=48000,aformat=sample_fmts=s32p:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a0];[1:a]aresample=48000,aformat=sample_fmts=s32p:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a1];[a0][a1]concat=n=2:v=0:a=1[outa]' -map '[outa]' -c:a alac -y "$LOSSLESS"
LCODEC="$($FFPROBE -v error -select_streams a:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$LOSSLESS")"
[[ "$LCODEC" == "alac" ]] || fail "lossless fallback codec is $LCODEC, expected alac"
pass 'mismatched audio fallback is ALAC, not AAC'

REF="$TMP/ref.mkv"; HEVC="$TMP/fidelity.mp4"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=640x360:rate=30' -t 1.5 -an -c:v ffv1 -pix_fmt yuv420p -y "$REF"
if "$FFMPEG" -hide_banner -loglevel error -i "$REF" -an -c:v hevc_videotoolbox -realtime 1 -prio_speed 1 -power_efficient 0 -q:v 95 -g 300 -tag:v hvc1 -pix_fmt yuv420p -y "$HEVC"; then
  SSIM="$($FFMPEG -hide_banner -i "$HEVC" -i "$REF" -lavfi '[0:v][1:v]ssim' -f null - 2>&1 | sed -n 's/.*All:\([0-9.]*\).*/\1/p' | tail -1)"
  [[ -n "$SSIM" ]] || fail 'could not read HEVC SSIM'
  python3 - "$SSIM" <<'PY'
import sys
v=float(sys.argv[1])
if v < 0.985:
    raise SystemExit(f'FAIL: fidelity HEVC SSIM too low: {v}')
print(f'PASS: fidelity HEVC SSIM {v:.6f}')
PY
else
  fail 'hevc_videotoolbox q95 fidelity smoke encode failed'
fi

echo 'ENDLUME Original Fidelity 8.27 release gates passed.'
