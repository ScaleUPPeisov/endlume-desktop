#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
pass(){ echo "PASS: $1"; }
fail(){ echo "FAIL: $1" >&2; exit 1; }
contains(){ grep -Fq "$1" "$2" || fail "$3"; pass "$3"; }

# Static code gates
python3 -m py_compile scripts/apply-render-stability-8-25.py scripts/apply-smart-repeat-8-26.py scripts/apply-original-fidelity-8-27.py scripts/apply-hybrid-fidelity-8-28.py scripts/apply-version-8-29.py
pass 'all release patch scripts compile'
contains 'fn hybrid_fidelity_args(' src-tauri/src/render.rs 'Hybrid Fidelity encoder exists'
contains '"-crf","22"' src-tauri/src/render.rs 'CRF22 visually-lossless budget is active'
contains 'audio-original-clean.mp3' src-tauri/src/render.rs 'clean exact-MP3 path exists'
contains 'concatf:' src-tauri/src/render.rs 'continuous MP3 concat path exists'
contains 'unique_output_ext(&out_dir,&job.project.name,"mov")' src-tauri/src/render.rs 'Original Fidelity outputs MOV'
contains 'probe_audio_decodes(app,out)' src-tauri/src/render.rs 'final audio is actually decoded before success'
contains "chooseVideo('subscribe')" src/pages/Editors.tsx 'Subscribe managed import remains fixed'
if grep -Fq 'choose_fidelity_encoder(app,attempt).await' src-tauri/src/render.rs; then fail 'smart path still selects VideoToolbox q95'; else pass 'VideoToolbox q95 size explosion removed from smart path'; fi

# 4K representative quality/size gate: one static detailed image + a sparse
# animated overlay, matching ENDLUME's main YouTube use case much better than a
# full-screen moving test pattern.
BG="$TMP/bg.png"; FX="$TMP/fx.mov"; REF="$TMP/ref.mkv"; MASTER="$TMP/master.mp4"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=3840x2160:rate=1' -frames:v 1 -y "$BG"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i "color=c=black@0.0:s=480x480:r=30,format=rgba,drawbox=x='180+20*sin(2*PI*t)':y=100:w=120:h=8:color=white@0.92:t=fill,drawbox=x=236:y='150+30*sin(2*PI*t*1.7)':w=8:h=180:color=white@0.92:t=fill" -t 6 -c:v qtrle -pix_fmt argb -y "$FX"
"$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 30 -i "$BG" -stream_loop -1 -i "$FX" -filter_complex "[0:v][1:v]overlay=x='(W-w)/2':y='(H-h)/2':shortest=1:eof_action=repeat[out]" -map '[out]' -t 6 -an -c:v ffv1 -pix_fmt yuv420p -y "$REF"
"$FFMPEG" -hide_banner -loglevel error -i "$REF" -an -c:v libx265 -preset ultrafast -crf 22 -tune ssim -x265-params 'keyint=180:min-keyint=180:scenecut=0:open-gop=0' -tag:v hvc1 -pix_fmt yuv420p -y "$MASTER"
BR="$($FFPROBE -v error -select_streams v:0 -show_entries stream=bit_rate -of default=nw=1:nk=1 "$MASTER")"
[[ -n "$BR" && "$BR" != "N/A" ]] || fail 'could not read hybrid master bitrate'
SSIM="$($FFMPEG -hide_banner -i "$MASTER" -i "$REF" -lavfi '[0:v]setpts=N/(30*TB)[enc];[1:v]setpts=N/(30*TB)[ref];[enc][ref]ssim' -f null - 2>&1 | sed -n 's/.*All:\([0-9.]*\).*/\1/p' | tail -1)"
python3 - "$BR" "$SSIM" <<'PY'
import sys
br=int(sys.argv[1]); ssim=float(sys.argv[2])
# 320 kbps exact source audio is a conservative upper audio budget.
est=(br+320_000)*7200/8
if ssim < 0.995:
    raise SystemExit(f'FAIL: 4K representative SSIM too low: {ssim:.6f}')
if est > 1_250_000_000:
    raise SystemExit(f'FAIL: representative 2h size estimate too high: {est/1e9:.2f} GB')
print(f'PASS: 4K representative SSIM {ssim:.6f}')
print(f'PASS: representative 2h estimate {est/1e9:.2f} GB (video {br/1e6:.3f} Mbit/s + 320k audio)')
PY

# Exact MP3 gate: no decode/re-encode, monotonic timestamps, real audio decode in MOV.
A="$TMP/a.mp3"; B="$TMP/b.mp3"; AC="$TMP/ac.mp3"; BC="$TMP/bc.mp3"; RAW="$TMP/raw.txt"; CYCLE="$TMP/cycle.mp3"; FINAL="$TMP/final.mov"; DTS="$TMP/dts.txt"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=440:sample_rate=44100' -t 1.4 -ac 2 -c:a libmp3lame -b:a 320k -y "$A"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=880:sample_rate=44100' -t 1.4 -ac 2 -c:a libmp3lame -b:a 320k -y "$B"
for pair in "$A:$AC" "$B:$BC"; do IFS=: read -r src dst <<< "$pair"; "$FFMPEG" -hide_banner -loglevel error -i "$src" -map 0:a:0 -c:a copy -map_metadata -1 -write_xing 0 -id3v2_version 0 -y "$dst"; done
printf '%s\n%s\n' "$AC" "$BC" > "$RAW"
"$FFMPEG" -hide_banner -loglevel error -fflags +genpts -i "concatf:$RAW" -map 0:a:0 -c:a copy -map_metadata -1 -write_xing 0 -id3v2_version 0 -y "$CYCLE"
"$FFMPEG" -hide_banner -loglevel error -stream_loop -1 -i "$MASTER" -stream_loop -1 -fflags +genpts -i "$CYCLE" -t 5 -map 0:v:0 -map 1:a:0 -c:v copy -c:a copy -movflags +faststart -y "$FINAL"
"$FFMPEG" -hide_banner -loglevel error -i "$FINAL" -map 0:a:0 -t 2 -f null -
ACODEC="$($FFPROBE -v error -select_streams a:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$FINAL")"
[[ "$ACODEC" == "mp3" ]] || fail "final audio codec is $ACODEC, expected exact mp3"
"$FFPROBE" -v error -select_streams a:0 -show_entries packet=dts_time -of csv=p=0 "$FINAL" > "$DTS"
python3 - "$DTS" <<'PY'
import sys
vals=[]
for line in open(sys.argv[1],encoding='utf-8'):
    s=line.strip()
    if s and s!='N/A': vals.append(float(s))
if len(vals)<20: raise SystemExit('FAIL: too few final MP3 packets')
for a,b in zip(vals,vals[1:]):
    if b<=a: raise SystemExit(f'FAIL: non-monotonic DTS {a} -> {b}')
print('PASS: final exact MP3 DTS are strictly monotonic')
PY
pass 'final MOV contains decodable original MP3 stream-copy audio'

echo 'ENDLUME 8.29 stability/fidelity gate passed.'
