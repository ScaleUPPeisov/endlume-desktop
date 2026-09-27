#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
fail(){ echo "8.41 validation failed: $1" >&2; exit 1; }
pass(){ echo "PASS: $1"; }

for f in src-tauri/src/render.rs src-tauri/src/cache.rs src-tauri/src/live_preview.rs src-tauri/src/persistence.rs src/store.ts src/pages/App.tsx src/pages/Editors.tsx src/pages/SettingsPage.tsx src/components/LiveCompositePreview.tsx src/tauri.ts src-tauri/tauri.conf.json updates/github/bootstrap.json package.json; do
  [[ -f "$f" ]] || fail "missing $f"
done

R=src-tauri/src/render.rs
C=src-tauri/src/cache.rs
LP=src-tauri/src/live_preview.rs
P=src-tauri/src/persistence.rs
S=src/store.ts
A=src/pages/App.tsx
E=src/pages/Editors.tsx
L=src/components/LiveCompositePreview.tsx
SET=src/pages/SettingsPage.tsx

# 1 + 8: 60fps without touching the proven speed/size budget.
grep -Fq 'resolved_job.settings.fps=60;' "$R" || fail 'true 60 FPS runtime lock missing'
if grep -Fq 'resolved_job.settings.fps=resolved_job.settings.fps.min(30);' "$R"; then fail '30 FPS runtime clamp survived'; fi
grep -Fq 'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}' "$R" || fail '500k proven video budget changed'
grep -Fq '"-maxrate","500k","-bufsize","4M"' "$R" || fail 'x265 500k/4M quality-size guard changed'
grep -Fq '"-b:v","500k","-maxrate","4M","-bufsize","16M"' "$R" || fail 'VideoToolbox 500k budget changed'
if grep -Fq 'fn hybrid_video_kbps(_s:&RenderSettings)->u64{700}' "$R"; then fail 'old 700k 8.39 size increase returned'; fi
grep -Fq 'force_original_aspect_ratio=increase' "$R" || fail '16:9 Fill scale missing'
grep -Fq 'crop={}:{}:(iw-ow)/2:(ih-oh)/2' "$R" || fail '16:9 Fill crop missing'
pass '60 FPS enabled while 8.36 speed/size/1080p budget stays unchanged'

# 4 + 7: real audio crossfade, continuous timeline and preserved video xfade path.
if grep -Fq 'resolved_job.settings.crossfade_sec=0.0;' "$R"; then fail 'crossfade is still disabled by Strict Fidelity'; fi
grep -Fq 'acrossfade=d={cf}:c1=tri:c2=tri' "$R" || fail 'audio acrossfade missing'
grep -Fq 'audio-crossfade-gapless.m4a' "$R" || fail 'HQ crossfade cycle missing'
grep -Fq 'materialize_continuous_audio' "$R" || fail 'continuous audio materializer missing'
grep -Fq '"-fflags","+genpts"' "$R" || fail 'generated audio timestamps missing'
grep -Fq '"-avoid_negative_ts","make_zero"' "$R" || fail 'audio timestamp zeroing missing'
grep -Fq 'audio_encoder_args(&audio_encoder)' "$R" || fail 'HQ platform audio encoder not used'
grep -Fq 'xfade=transition=fade:duration={cf}' "$R" || fail 'existing visual xfade transition path missing'
pass 'audio crossfade/gapless path + existing visual xfade transition preserved'

# 2 + 6: 100+ project history must not block WKWebView/localStorage.
grep -Fq 'version:6,migrate:' "$S" || fail 'Zustand v6 cleanup migration missing'
grep -Fq 'p.projects=[]' "$S" || fail 'old persisted render history is not discarded'
# IMPORTANT: do not grep the whole store for "projects:s.projects" because normal
# state updates such as patchProject legitimately contain that substring. Inspect
# only the persist partialize expression.
python3 - "$S" <<'PY' || fail 'projects are still persisted to localStorage'
from pathlib import Path
import re,sys
s=Path(sys.argv[1]).read_text(encoding='utf-8')
m=re.search(r"partialize:\(s\)=>\(\{([^}]*)\}\)",s,re.S)
if not m:
    raise SystemExit('partialize expression missing')
body=m.group(1)
if re.search(r'(^|,)\s*projects\s*:',body):
    raise SystemExit('projects key present in persist partialize')
print('PASS: persist partialize excludes projects')
PY
grep -Fq 'requestAnimationFrame(flushRenderProgress)' "$A" || fail 'render progress is not animation-frame batched'
if grep -Fq 'window.setTimeout(flushRenderProgress,50)' "$A"; then fail 'old 20fps progress timer returned'; fi
grep -Fq 'content-visibility:auto!important' src/motion-polish.css || fail 'large queue paint virtualization missing'
pass '100+ project UI persistence/progress bottleneck removed'

# 3: Effects/Equalizer true-motion 60 FPS rather than duplicate fps filter only.
grep -Fq 'minterpolate=fps={fps}:mi_mode=mci' "$C" || fail 'render Effects motion interpolation missing'
grep -Fq 'minterpolate=fps=60:mi_mode=mci' "$LP" || fail 'Live Preview motion interpolation missing'
pass 'Effects/Equalizer render + preview use motion-interpolated 60 FPS'

# 9: chroma despill must persist and match Preview/Render cache.
grep -Fq 'despill=type={}:mix={}:expand=0.20' "$C" || fail 'FFmpeg despill missing'
grep -Fq 'aspect-safe-v6-motion' "$C" || fail 'new chroma/motion cache generation missing'
grep -Fq 'despill<=0.0' "$P" || fail 'despill persistence migration missing'
grep -Fq 'json!(0.35)' "$P" || fail 'despill default 0.35 missing'
[[ "$(grep -Fc 'Despill / убрать зелёный ореол' "$E")" -ge 2 ]] || fail 'despill controls missing from Effects/Subscribe'
grep -Fq 'uniform float dsp' "$L" || fail 'WebGL preview despill missing'
grep -Fq 'gl.uniform1f(uDsp' "$L" || fail 'WebGL despill value not wired'
pass 'chromakey despill fixed in persistence, render cache and Live Preview'

# 5: updater remains native Tauri signed updater. No local builder calls in frontend.
python3 - <<'PY'
import json
EXPECTED='https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/latest.json'
b=json.load(open('updates/github/bootstrap.json'))
c=json.load(open('src-tauri/tauri.conf.json'))
u=c.get('plugins',{}).get('updater',{})
assert u.get('endpoints')==[EXPECTED],u.get('endpoints')
assert u.get('pubkey')==b.get('pubkey') and u.get('pubkey')
assert c.get('bundle',{}).get('createUpdaterArtifacts') is True
PY
grep -Fq 'downloadAndInstall' src/tauri.ts || fail 'native download/install missing'
grep -Fq 'await relaunch()' src/tauri.ts || fail 'native relaunch missing'
if grep -Eq 'local_update_(check|start|status)' src/tauri.ts; then fail 'old local updater frontend returned'; fi
pass 'native signed online updater preserved'

# 10 + version.
grep -Fq 'Kirill Peisov' "$SET" || fail 'creator missing'
grep -Fq 'peisov.business@gmail.com' "$SET" || fail 'creator email missing'
grep -Fq '1.0.0-alpha.8.41' package.json || fail 'package version is not 8.41'
grep -Fq '1.0.0-alpha.8.41' src-tauri/tauri.conf.json || fail 'Tauri version is not 8.41'
pass 'About + version 8.41 correct'

# Guard unrelated accepted contracts.
if grep -Eq 'Noise 1|Noise 2|Шум 1|Шум 2' src/pages/Editors.tsx src/pages/ProjectPage.tsx src/store.ts "$R"; then fail 'Noise 1/2 regression'; fi
pass 'Noise 1/2 remain removed; unrelated UI contract preserved'

# Real FFmpeg smoke: 30fps motion -> 60fps interpolation and audio acrossfade.
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
VID="$TMP/motion60.mp4"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=s=320x180:r=30' -t 2 -vf 'minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1' -c:v libx264 -preset ultrafast -crf 18 -pix_fmt yuv420p -y "$VID"
RATE="$("$FFPROBE" -v error -select_streams v:0 -show_entries stream=avg_frame_rate -of default=nw=1:nk=1 "$VID")"
python3 - "$RATE" <<'PY'
import sys
r=sys.argv[1].strip(); a,b=(r.split('/')+['1'])[:2]; fps=float(a)/max(float(b),1e-9)
print(f'PASS: interpolated smoke avg_frame_rate={fps:.3f}')
if not 59.0<=fps<=61.0: raise SystemExit('FAIL: interpolation output is not 60fps')
PY
AUD="$TMP/crossfade.m4a"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'sine=frequency=440:sample_rate=48000:duration=3' -f lavfi -i 'sine=frequency=660:sample_rate=48000:duration=3' -filter_complex '[0:a]asetpts=N/SR/TB[a0];[1:a]asetpts=N/SR/TB[a1];[a0][a1]acrossfade=d=1:c1=tri:c2=tri,aresample=48000:async=1:first_pts=0[out]' -map '[out]' -c:a aac -b:a 320k -y "$AUD"
DUR="$("$FFPROBE" -v error -show_entries format=duration -of default=nw=1:nk=1 "$AUD")"
python3 - "$DUR" <<'PY'
import sys
d=float(sys.argv[1]); print(f'PASS: crossfade smoke duration={d:.3f}s')
if not 4.7<=d<=5.3: raise SystemExit('FAIL: crossfade duration unexpected')
PY

# Budget projection stays under 1 GB for 2:02:03 at 500k video + 320k audio.
python3 - <<'PY'
sec=2*3600+2*60+3
mb=(500_000+320_000)*sec/8/1_000_000
print(f'PASS: nominal 2:02:03 payload budget={mb:.1f} MB before container overhead')
if mb>=1000: raise SystemExit('FAIL: nominal payload budget >= 1GB')
PY

echo '✅ ENDLUME 8.41 full targeted regression gate passed'
