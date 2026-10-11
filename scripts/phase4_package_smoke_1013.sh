#!/bin/bash
set -Eeuo pipefail
export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.cargo/bin:$PATH"
STAGE="${PHASE4_STAGE:?PHASE4_STAGE missing}"
UNPACK="$RUNNER_TEMP/endlume-1013-package-unpack"
rm -rf "$UNPACK"; mkdir -p "$UNPACK"
/usr/bin/ditto -x -k "$STAGE/ENDLUME-10.0.13-macos-aarch64.app.zip" "$UNPACK"
APP="$(find "$UNPACK" -maxdepth 2 -type d -name '*.app' -print -quit)"
[ -d "$APP" ]
/usr/bin/codesign --verify --deep --strict "$APP"
EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$APP/Contents/Info.plist")"
ROOT="$RUNNER_TEMP/endlume-1013-package-smoke"
rm -rf "$ROOT"; mkdir -p "$ROOT/media" "$ROOT/out" "$ROOT/jobs" "$ROOT/results" "$ROOT/home"
FFMPEG="$APP/Contents/MacOS/ffmpeg"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x182033:s=1920x1080' -frames:v 1 -y "$ROOT/media/cover.png"
for I in $(seq 1 10); do
  HZ=$((200 + I*23))
  "$FFMPEG" -hide_banner -loglevel error -f lavfi -i "sine=frequency=$HZ:sample_rate=48000:duration=10" -c:a libmp3lame -b:a 320k -ar 48000 -ac 2 -y "$ROOT/media/track-$I.mp3"
done
python3 - "$ROOT" <<'PY'
import json,sys
from pathlib import Path
r=Path(sys.argv[1]); tracks=sorted(str(x) for x in (r/'media').glob('track-*.mp3'))
job={'project':{'id':'release-smoke','name':'ENDLUME 10.0.13 Package Smoke','path':str(r/'media'),'media':[str(r/'media'/'cover.png')],'audio':tracks,'valid':True,'error':None,'anchors':None,'selectedEffectId':'__none__'},'settings':{'width':1920,'height':1080,'fps':60,'codec':'h265','bitrateMbps':30.0,'durationHours':3.0,'durationMode':'whole-track','loopMode':'image','crossfadeSec':0.0,'normalizeLufs':False,'outputDir':str(r/'out'),'preset':'fast','encoderPreference':'auto'},'effects':[],'subscribes':[],'ambient':None,'ambientSettings':{'volumePct':18.0,'bassDb':0.0,'midDb':0.0,'trebleDb':0.0}}
(r/'jobs'/'render.json').write_text(json.dumps(job))
PY
export HOME="$ROOT/home"
export CFFIXED_USER_HOME="$ROOT/home"
export XDG_DATA_HOME="$ROOT/home/.local/share"
export XDG_CONFIG_HOME="$ROOT/home/.config"
export XDG_CACHE_HOME="$ROOT/home/.cache"
export ENDLUME_E2E_RENDER_JOB="$ROOT/jobs/render.json"
export ENDLUME_E2E_RESULT="$ROOT/results/render.json"
"$APP/Contents/MacOS/$EXE" >"$ROOT/stdout.log" 2>"$ROOT/stderr.log"
python3 - "$ROOT/results/render.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); assert d['status']=='passed',d
rows=d.get('results',[]); assert len(rows)==1 and rows[0]['status']=='passed',rows
r=rows[0]
assert r.get('fastPath') is True,r
assert r.get('videoCodec')=='hevc',r
assert r.get('audioMode')=='mp3-packet-copy',r
assert float(r.get('wallSeconds',999))<=10.0,r
print('FAST_PATH=YES')
print('FAST_SMOKE_WALL_SECONDS='+str(r.get('wallSeconds')))
print('FAST_SMOKE_OUTPUT='+str(r.get('outputPath')))
PY
OUT="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d["results"][0]["outputPath"])' "$ROOT/results/render.json")"
[ -s "$OUT" ]
"$APP/Contents/MacOS/ffprobe" -v error -select_streams v:0 -show_entries stream=codec_name,width,height,r_frame_rate -of default=nw=1 "$OUT" | tee "$ROOT/probe.txt"
grep -q 'codec_name=hevc' "$ROOT/probe.txt"
grep -q 'width=1920' "$ROOT/probe.txt"
grep -q 'height=1080' "$ROOT/probe.txt"
grep -q 'r_frame_rate=60/1' "$ROOT/probe.txt"
"$FFMPEG" -hide_banner -v error -ss 3600 -i "$OUT" -t 0.25 -map 0:v:0 -map 0:a:0 -f null -
echo FAST_ENGINE_PACKAGED=PASS
echo OUTPUT_OPEN_SEEK=PASS
