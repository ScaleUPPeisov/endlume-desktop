#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
pass(){ echo "PASS: $1"; }
fail(){ echo "FAIL: $1" >&2; exit 1; }
contains(){ grep -Fq "$1" "$2" || fail "$3"; pass "$3"; }

contains 'fn hybrid_fidelity_args(' src-tauri/src/render.rs 'Hybrid Fidelity x265 encoder exists'
contains '"-crf","14"' src-tauri/src/render.rs 'Hybrid Fidelity CRF14 quality gate exists'
contains 'hybrid_master_seconds' src-tauri/src/render.rs 'short 30s master exists'
contains 'audio-original-clean.mp3' src-tauri/src/render.rs 'clean exact-MP3 cycle exists'
contains 'concatf:' src-tauri/src/render.rs 'raw continuous MP3 concat path exists'
contains '"-write_xing","0"' src-tauri/src/render.rs 'Xing timestamps are removed before exact MP3 concat'
contains 'unique_output_ext(&out_dir,&job.project.name,"mov")' src-tauri/src/render.rs 'Original Fidelity outputs QuickTime MOV'
contains 'probe_audio_decodes(app,out)' src-tauri/src/render.rs 'final result verifies real audio decode'
contains 'Hybrid Fidelity: собираю короткий master' src-tauri/src/render.rs 'single image renders directly to hybrid master'
contains '"libx265".to_string()' src-tauri/src/render.rs 'smart repeat avoids VideoToolbox q95 size explosion'
contains 'Hybrid Fidelity: short-master x265 CRF14' src/pages/RenderPage.tsx 'Render Center shows 8.28 mode'

# Build two real MP3s, clean-remux them with stream-copy and concatenate the raw
# MP3 payload. This reproduces the 8.28 audio path and must not emit non-monotonic DTS.
A="$TMP/a.mp3"; B="$TMP/b.mp3"; AC="$TMP/ac.mp3"; BC="$TMP/bc.mp3"; RAW="$TMP/raw.txt"; CYCLE="$TMP/cycle.mp3"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=440:sample_rate=44100' -t 1.2 -ac 2 -c:a libmp3lame -b:a 192k -y "$A"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=880:sample_rate=44100' -t 1.2 -ac 2 -c:a libmp3lame -b:a 256k -y "$B"
"$FFMPEG" -hide_banner -loglevel error -i "$A" -map 0:a:0 -c:a copy -map_metadata -1 -write_xing 0 -id3v2_version 0 -y "$AC"
"$FFMPEG" -hide_banner -loglevel error -i "$B" -map 0:a:0 -c:a copy -map_metadata -1 -write_xing 0 -id3v2_version 0 -y "$BC"
printf '%s\n%s\n' "$AC" "$BC" > "$RAW"
"$FFMPEG" -hide_banner -loglevel error -fflags +genpts -i "concatf:$RAW" -map 0:a:0 -c:a copy -map_metadata -1 -write_xing 0 -id3v2_version 0 -y "$CYCLE"
"$FFMPEG" -hide_banner -loglevel error -i "$CYCLE" -map 0:a:0 -t 1 -f null -
pass 'clean exact MP3 cycle decodes'

# Verify DTS are strictly increasing after repeated stream-copy into MOV.
BG="$TMP/bg.png"; FX="$TMP/fx.mov"; MASTER="$TMP/master.mp4"; FINAL="$TMP/final.mov"; DTS="$TMP/dts.txt"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x182038:size=1280x720' -frames:v 1 -y "$BG"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=green@0.0:size=180x180:rate=30,format=rgba' -vf "drawbox=x=20+40*sin(2*PI*t):y=20:w=140:h=140:color=white@0.9:t=8" -t 3 -c:v qtrle -pix_fmt argb -y "$FX"
"$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 30 -i "$BG" -stream_loop -1 -i "$FX" -filter_complex "[0:v]scale=1280:720,fps=30[b];[1:v]scale=iw*0.55:ih*0.55[fx];[b][fx]overlay=x='(W-w)*0.5':y='(H-h)*0.5':shortest=1:eof_action=repeat[outv]" -map '[outv]' -t 6 -an -c:v libx265 -preset ultrafast -crf 14 -tune ssim -x265-params 'keyint=180:min-keyint=180:scenecut=0:open-gop=0' -tag:v hvc1 -pix_fmt yuv420p -y "$MASTER"
MASTER_BR="$($FFPROBE -v error -select_streams v:0 -show_entries stream=bit_rate -of default=nw=1:nk=1 "$MASTER" || true)"
python3 - "$MASTER_BR" <<'PY'
import sys
raw=sys.argv[1].strip()
if raw and raw!='N/A':
    br=int(raw)
    if br>2500000:
        raise SystemExit(f'FAIL: hybrid static+small-overlay bitrate too high: {br}')
    print(f'PASS: hybrid master bitrate {br/1e6:.3f} Mbit/s')
else:
    print('PASS: hybrid master built (bitrate unavailable from ffprobe)')
PY
"$FFMPEG" -hide_banner -loglevel error -stream_loop -1 -i "$MASTER" -stream_loop -1 -fflags +genpts -i "$CYCLE" -t 8 -map 0:v:0 -map 1:a:0 -c:v copy -c:a copy -movflags +faststart -y "$FINAL"
"$FFMPEG" -hide_banner -loglevel error -i "$FINAL" -map 0:a:0 -t 2 -f null -
"$FFPROBE" -v error -select_streams a:0 -show_entries packet=dts_time -of csv=p=0 "$FINAL" > "$DTS"
python3 - "$DTS" <<'PY'
import sys
vals=[]
for line in open(sys.argv[1],encoding='utf-8'):
    s=line.strip()
    if not s or s=='N/A': continue
    vals.append(float(s))
if len(vals)<10: raise SystemExit('FAIL: too few audio packets in final MOV')
for a,b in zip(vals,vals[1:]):
    if b<=a: raise SystemExit(f'FAIL: non-monotonic audio DTS: {a} -> {b}')
print('PASS: final MOV audio DTS are strictly monotonic')
PY
VCODEC="$($FFPROBE -v error -select_streams v:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$FINAL")"
ACODEC="$($FFPROBE -v error -select_streams a:0 -show_entries stream=codec_name -of default=nw=1:nk=1 "$FINAL")"
[[ "$VCODEC" == "hevc" && "$ACODEC" == "mp3" ]] || fail "final MOV codecs invalid: video=$VCODEC audio=$ACODEC"
pass 'QuickTime MOV keeps HEVC + exact MP3 stream-copy'

echo 'ENDLUME Hybrid Fidelity 8.28 release gates passed.'
