#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
fail(){ echo "FAIL: $1" >&2; exit 1; }
pass(){ echo "PASS: $1"; }

RUST=src-tauri/src/render.rs
CACHE=src-tauri/src/cache.rs
STORE=src/store.ts
APP=src/pages/App.tsx
EDITORS=src/pages/Editors.tsx
LIVE=src/components/LiveCompositePreview.tsx
SETTINGS=src/pages/SettingsPage.tsx
UPD=src-tauri/src/updater_local.rs
PKG=package.json
for f in "$RUST" "$CACHE" "$STORE" "$APP" "$EDITORS" "$LIVE" "$SETTINGS" "$UPD" "$PKG"; do test -f "$f" || fail "missing $f"; done

grep -Fq 'resolved_job.settings.width=1920;' "$RUST" || fail 'runtime width is not locked to 1920'
grep -Fq 'resolved_job.settings.height=1080;' "$RUST" || fail 'runtime height is not locked to 1080'
grep -Fq 'resolved_job.settings.fps=60;' "$RUST" || fail 'smart-repeat is not true 60 FPS'
! grep -Fq 'resolved_job.settings.fps=resolved_job.settings.fps.min(30)' "$RUST" || fail 'old 30 FPS clamp survived'
grep -Fq 'force_original_aspect_ratio=increase' "$RUST" || fail 'YouTube Fill cover scale missing'
grep -Fq 'crop={}:{}:(iw-ow)/2:(ih-oh)/2' "$RUST" || fail 'center crop missing'
! grep -Fq 'pad={}:{}' "$RUST" || fail 'black-bar pad returned'
grep -Fq 'flags=lanczos+accurate_rnd' "$RUST" || fail 'Lanczos source scaling missing'
grep -Fq '"-crf","18"' "$RUST" || fail 'first-frame CRF18 quality path missing'
grep -Fq '"-maxrate","700k"' "$RUST" || fail '60 FPS overlay bitrate headroom missing'
pass '1920x1080 / 60 FPS / no-bars / image-quality wiring preserved'

grep -Fq 'crossfadeSec:3' "$STORE" || fail 'crossfade default is not 3 sec'
grep -Fq "fps:60,codec:'h265'" "$STORE" || fail 'UI default is not 1080p60 HEVC'
grep -Fq 'version:5,migrate:' "$STORE" || fail 'anti-freeze persisted-state migration missing'
grep -Fq 'p.projects=[]' "$STORE" || fail 'old large project history is not dropped'
TAIL="$(grep -o "name:'endlume-1-ui'.*" "$STORE" || true)"
[[ "$TAIL" != *'projects:s.projects'* ]] || fail 'project history is still persisted on every progress event'
grep -Fq 'window.setTimeout(flushRenderProgress,50)' "$APP" || fail 'render-progress batching missing'
grep -Fq 'progressPending.clear()' "$APP" || fail 'render-progress batch cleanup missing'
pass '100-job UI freeze protection and progress batching are wired'

grep -Fq 'audio-crossfade-gapless.m4a' "$RUST" || fail 'gapless crossfade cycle missing'
grep -Fq 'aresample=48000:async=1:first_pts=0' "$RUST" || fail 'audio timestamp normalization missing'
grep -Fq '"-c:a","aac","-b:a","320k"' "$RUST" || fail 'HQ 320k crossfade audio codec missing'
grep -Fq 'audio-continuous.m4a' "$RUST" || fail 'continuous materialized audio timeline missing'
grep -Fq '"-fflags","+genpts","-avoid_negative_ts","make_zero"' "$RUST" || fail 'continuous audio timestamp guards missing'
grep -Fq 'Original Audio: копирую MP3 без перекодирования' "$RUST" || fail 'exact MP3 copy path for crossfade-off was lost'
! grep -Fq 'resolved_job.settings.crossfade_sec=0.0;' "$RUST" || fail 'runtime still disables crossfade'
pass 'real crossfade + no-gap timeline + exact MP3-off path are wired'

grep -Fq 'despill=type={}:mix={}:expand=0.20' "$RUST" || fail 'render despill missing'
grep -Fq 'aspect-safe-v5' "$CACHE" || fail 'despill-aware cache fingerprint missing'
grep -Fq 'despill=type={}:mix={}:expand=0.20' "$CACHE" || fail 'cache despill missing'
grep -Fq 'Despill / убрать зелёный ореол' "$EDITORS" || fail 'despill control missing'
grep -Fq 'uniform float dsp' "$LIVE" || fail 'Live Preview despill shader missing'
grep -Fq 'gl.uniform1f(uDsp' "$LIVE" || fail 'Live Preview despill uniform missing'
"$FFMPEG" -hide_banner -filters 2>/dev/null | grep -q '[[:space:]]despill[[:space:]]' || fail 'bundled FFmpeg has no despill filter'
pass 'chromakey despill is matched across Render / cache / Live Preview'

grep -Fq 'Kirill Peisov' "$SETTINGS" || fail 'creator missing from About'
grep -Fq 'peisov.business@gmail.com' "$SETTINGS" || fail 'creator email missing from About'
grep -Fq 'remote_release_ready' "$UPD" || fail 'hybrid updater remote binary probe missing'
grep -Fq 'launch_remote' "$UPD" || fail 'hybrid updater remote install path missing'
grep -Fq 'launch_local' "$UPD" || fail 'hybrid updater local fallback missing'
grep -Fq 'valid_builder' "$UPD" || fail 'hybrid updater builder safety guard missing'
grep -Fq 'release download' "$UPD" || fail 'Remote Update Center prebuilt download missing'
grep -Eq '"version": "1\.0\.0-alpha\.8\.39"' "$PKG" || fail 'package version is not 8.39'
pass 'About owner info + hybrid in-app updater are preserved'

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=1920x1080:rate=60' -frames:v 1 -y "$TMP/base.png"
START="$(python3 - <<'PY'
import time
print(time.time())
PY
)"
"$FFMPEG" -hide_banner -loglevel error -loop 1 -framerate 60 -i "$TMP/base.png" -t 6 -an \
  -vf 'scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop=1920:1080:(iw-ow)/2:(ih-oh)/2,fps=60,setsar=1' \
  -c:v libx265 -preset ultrafast -crf 18 -maxrate 700k -bufsize 8M \
  -x265-params 'keyint=360:min-keyint=360:scenecut=0:open-gop=0:aq-mode=3:aq-strength=1.0:vbv-init=1.0' \
  -tag:v hvc1 -pix_fmt yuv420p -y "$TMP/60fps.mp4"
END="$(python3 - <<'PY'
import time
print(time.time())
PY
)"
DIM="$("$FFPROBE" -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "$TMP/60fps.mp4")"
FPS="$("$FFPROBE" -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=nw=1:nk=1 "$TMP/60fps.mp4")"
[[ "$DIM" == '1920x1080' ]] || fail "60 FPS master dimensions: $DIM"
[[ "$FPS" == '60/1' ]] || fail "master frame rate is $FPS instead of 60/1"
python3 - "$START" "$END" <<'PY'
import sys
sec=float(sys.argv[2])-float(sys.argv[1])
print(f'PASS: 6s 1080p60 short master encoded in {sec:.2f}s')
if sec>25:
    raise SystemExit(f'FAIL: short-master encode too slow: {sec:.2f}s')
PY

"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=720x1280:rate=1' -frames:v 1 \
  -vf 'scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop=1920:1080:(iw-ow)/2:(ih-oh)/2,setsar=1' -y "$TMP/portrait.png"
PDIM="$("$FFPROBE" -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "$TMP/portrait.png")"
[[ "$PDIM" == '1920x1080' ]] || fail "portrait cover/crop dimensions: $PDIM"
pass 'portrait input fills 1920x1080 without pad/black bars'

"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x00ff00:size=320x180:rate=60' -frames:v 2 \
  -vf 'format=rgba,colorkey=0x00ff00:0.10:0.06,despill=type=green:mix=0.35:expand=0.20,format=yuv420p' -f null -
pass 'FFmpeg chroma + despill pipeline executes'

"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=440:sample_rate=48000:duration=4' -ac 2 -c:a libmp3lame -b:a 320k -y "$TMP/a.mp3"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=733:sample_rate=48000:duration=4' -ac 2 -c:a libmp3lame -b:a 320k -y "$TMP/b.mp3"
"$FFMPEG" -hide_banner -loglevel error -i "$TMP/a.mp3" -i "$TMP/b.mp3" \
  -filter_complex '[0:a]aresample=48000:async=1:first_pts=0,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a0];[1:a]aresample=48000:async=1:first_pts=0,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asetpts=N/SR/TB[a1];[a0][a1]acrossfade=d=1.5:c1=tri:c2=tri,aresample=48000:async=1:first_pts=0,alimiter=limit=0.98[outa]' \
  -map '[outa]' -c:a aac -b:a 320k -ar 48000 -ac 2 -y "$TMP/crossfade.m4a"
"$FFMPEG" -hide_banner -loglevel info -i "$TMP/crossfade.m4a" -af 'silencedetect=noise=-55dB:d=0.15' -f null - 2>"$TMP/silence.log" || fail 'crossfade decode failed'
if grep -q 'silence_duration' "$TMP/silence.log"; then cat "$TMP/silence.log"; fail 'detectable silence exists in crossfade join'; fi
pass 'crossfade smoke contains no >=150ms silent interruption'

python3 - <<'PY'
seconds=2*3600+2*60+3
video=700_000
audio=320_000
payload=(video+audio)*seconds/8
print(f'PASS: projected 2:02:03 payload at 700k video + 320k audio = {payload/1e6:.1f} MB')
if payload>970_000_000:
    raise SystemExit(f'FAIL: projected payload too large: {payload}')
PY

echo 'ENDLUME 8.39 targeted 60FPS/stability/audio/chroma/hybrid-updater gate passed.'
