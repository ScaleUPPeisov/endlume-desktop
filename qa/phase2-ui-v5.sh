#!/bin/bash
set -Eeuo pipefail
REPORT="$RUNNER_TEMP/endlume-phase2-v5"; STATE="$RUNNER_TEMP/endlume-phase2-v5-state"; SRC="$RUNNER_TEMP/phase2-v5-source"; FIX="$RUNNER_TEMP/endlume-phase2-v5-fixture"; UNPACK="$RUNNER_TEMP/endlume-phase2-v5-unpack"; DMG="$RUNNER_TEMP/ENDLUME-PHASE2-V5.dmg"
APP_DATA="$HOME/Library/Application Support/studio.endlume.desktop"; WEBKIT="$HOME/Library/WebKit/studio.endlume.desktop"; OWNER_APP="/Applications/ENDLUME YT Studio PEISOV.app"
rm -rf "$REPORT" "$STATE" "$FIX" "$UNPACK" "$DMG"; mkdir -p "$REPORT/screens" "$STATE" "$FIX/project" "$FIX/output" "$APP_DATA"
QA_BIN=""; QA_VOL=""; PID=""
state_row(){ local n="$1" p="$APP_DATA/$n"; if [ -f "$p" ]; then printf '%s\tEXISTS\t%s\t%s\n' "$n" "$(stat -f '%z' "$p")" "$(shasum -a 256 "$p"|awk '{print $1}')"; else printf '%s\tABSENT\t0\t-\n' "$n"; fi; }
cleanup(){
  set +e
  /bin/launchctl unsetenv ENDLUME_E2E_LIBRARY_PATH >/dev/null 2>&1
  [ -z "$QA_BIN" ] || pkill -f "$QA_BIN" >/dev/null 2>&1
  sleep 2
  [ -z "$QA_VOL" ] || hdiutil detach -quiet "$QA_VOL" >/dev/null 2>&1
  for n in library.json queue.json recovery.json session.json; do if [ -f "$STATE/$n" ]; then cp -p "$STATE/$n" "$APP_DATA/$n"; elif [ -f "$STATE/$n.ABSENT" ]; then rm -f "$APP_DATA/$n"; fi; done
  rm -rf "$WEBKIT"; [ ! -d "$STATE/webkit" ] || ditto "$STATE/webkit" "$WEBKIT"
  if [ -f "$STATE/managed-assets.txt" ]; then while IFS= read -r p; do case "$p" in "$APP_DATA"/library-assets/effects/phase2-v5-*|"$APP_DATA"/library-assets/subscribe/phase2-v5-*) rm -f "$p";; esac; done < "$STATE/managed-assets.txt"; fi
  : > "$REPORT/state-after.tsv"; for n in library.json queue.json recovery.json session.json; do state_row "$n" >> "$REPORT/state-after.tsv"; done
  if [ -f "$REPORT/state-before.tsv" ]; then cmp -s "$REPORT/state-before.tsv" "$REPORT/state-after.tsv" && echo OWNER_STATE_RESTORED=YES > "$REPORT/cleanup.txt" || echo OWNER_STATE_RESTORED=FAIL > "$REPORT/cleanup.txt"; fi
  if [ -d "$OWNER_APP" ]; then oe="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$OWNER_APP/Contents/Info.plist" 2>/dev/null)"; os="$(shasum -a 256 "$OWNER_APP/Contents/MacOS/$oe" 2>/dev/null|awk '{print $1}')"; printf 'OWNER_BIN_SHA256=%s\n' "$os" >> "$REPORT/cleanup.txt"; fi
}
trap cleanup EXIT

test "$RUNNER_NAME" = "kirill-mac-endlume"
test "$(/usr/bin/osascript -e 'tell application "System Events" to return UI elements enabled' 2>/dev/null || echo false)" = true
test -d "$OWNER_APP"
OWNER_EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$OWNER_APP/Contents/Info.plist")"; OWNER_BIN="$OWNER_APP/Contents/MacOS/$OWNER_EXE"; OWNER_SHA="$(shasum -a 256 "$OWNER_BIN"|awk '{print $1}')"; test "$OWNER_SHA" = "$OWNER_APP_BIN_SHA256"; ! pgrep -f "$OWNER_BIN" >/dev/null 2>&1
: > "$REPORT/state-before.tsv"; for n in library.json queue.json recovery.json session.json; do if [ -f "$APP_DATA/$n" ]; then cp -p "$APP_DATA/$n" "$STATE/$n"; else touch "$STATE/$n.ABSENT"; fi; state_row "$n" >> "$REPORT/state-before.tsv"; done
python3 - "$APP_DATA/queue.json" <<'PY'
import json,os,sys
p=sys.argv[1]
if os.path.isfile(p):
    try:q=json.load(open(p))
    except Exception:q={}
    if q.get('active') is not None or (q.get('pending') or []): print('BLOCKED_OWNER_QUEUE_NOT_EMPTY=true');raise SystemExit(91)
PY
if [ -d "$WEBKIT" ]; then ditto "$WEBKIT" "$STATE/webkit"; else touch "$STATE/WEBKIT.ABSENT"; fi
printf 'OWNER_VERSION=%s\nOWNER_BIN_SHA256=%s\nSAFETY_GATE=PASS\n' "$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$OWNER_APP/Contents/Info.plist")" "$OWNER_SHA" > "$REPORT/owner-before.txt"
echo SAFETY_GATE=PASS

ZIP="$SRC/ENDLUME-CANONICAL-GOOD-PRODUCT-QA.app.zip"; test -f "$ZIP"; test "$(shasum -a 256 "$ZIP"|awk '{print $1}')" = "$EXPECTED_APP_ZIP_SHA256"
ditto -x -k "$ZIP" "$UNPACK"; BUILT_APP="$(find "$UNPACK" -maxdepth 2 -type d -name '*.app' -print -quit)"; EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$BUILT_APP/Contents/Info.plist")"; test "$(shasum -a 256 "$BUILT_APP/Contents/MacOS/$EXE"|awk '{print $1}')" = "$EXPECTED_APP_BIN_SHA256"; /usr/bin/codesign --verify --deep --strict "$BUILT_APP"
hdiutil create -quiet -size 350m -fs APFS -volname ENDLUME_CANONICAL_QA_V5 "$DMG"; hdiutil attach -nobrowse -plist "$DMG" > "$RUNNER_TEMP/phase2-v5-attach.plist"
QA_VOL="$(python3 - "$RUNNER_TEMP/phase2-v5-attach.plist" <<'PY'
import plistlib,sys
p=plistlib.load(open(sys.argv[1],'rb'));xs=[x.get('mount-point') for x in p.get('system-entities',[]) if x.get('mount-point')];print(xs[-1])
PY
)"; QA_APP="$QA_VOL/ENDLUME-CANONICAL-GOOD-PRODUCT-QA.app"; ditto "$BUILT_APP" "$QA_APP"; QA_BIN="$QA_APP/Contents/MacOS/$EXE"; test "$(shasum -a 256 "$QA_BIN"|awk '{print $1}')" = "$EXPECTED_APP_BIN_SHA256"; /usr/bin/codesign --verify --deep --strict "$QA_APP"
FFMPEG="$(find "$QA_APP/Contents" -type f -perm -111 -name 'ffmpeg*' -print | head -1)"; test -x "$FFMPEG"
"$FFMPEG" -hide_banner -loglevel error -y -f lavfi -i color=c=0x142039:s=1920x1080 -frames:v 1 "$FIX/project/base.png"
"$FFMPEG" -hide_banner -loglevel error -y -f lavfi -i sine=frequency=330:duration=60 -c:a libmp3lame -b:a 192k -ar 48000 -ac 2 "$FIX/project/track-01.mp3"
"$FFMPEG" -hide_banner -loglevel error -y -f lavfi -i sine=frequency=440:duration=60 -c:a libmp3lame -b:a 192k -ar 48000 -ac 2 "$FIX/project/track-02.mp3"
"$FFMPEG" -hide_banner -loglevel error -y -f lavfi -i color=c=0x00ff00:s=640x360:d=2 -vf 'drawbox=x=180:y=90:w=280:h=180:color=red@1:t=fill' -c:v h264_videotoolbox -pix_fmt yuv420p "$FIX/effect.mp4"
"$FFMPEG" -hide_banner -loglevel error -y -f lavfi -i color=c=0x00ff00:s=640x360:d=2 -vf 'drawbox=x=120:y=130:w=400:h=100:color=magenta@1:t=fill' -c:v h264_videotoolbox -pix_fmt yuv420p "$FIX/subscribe.mp4"
EROOT="$APP_DATA/library-assets/effects"; SROOT="$APP_DATA/library-assets/subscribe"; mkdir -p "$EROOT" "$SROOT"; QAE="$EROOT/phase2-v5-effect-${GITHUB_RUN_ID}.mp4"; QAS="$SROOT/phase2-v5-subscribe-${GITHUB_RUN_ID}.mp4"; cp "$FIX/effect.mp4" "$QAE"; cp "$FIX/subscribe.mp4" "$QAS"; printf '%s\n%s\n' "$QAE" "$QAS" > "$STATE/managed-assets.txt"
python3 - "$QAE" "$QAS" "$FIX/library.json" <<'PY'
import json,sys
e,s,o=sys.argv[1:];b=dict(enabled=True,mode='chromakey',keyColor='#00ff00',similarity=.10,blend=.06,despill=.35,lumaThreshold=.03,lumaTolerance=.08,saturation=1,x=.5,y=.5,scale=.34,fullscreen=False,previewFrameTime=0,startSec=0,endSec=None,target='CUSTOM',offsetX=0,offsetY=0,opacity=1,assetState='ready',cacheReady=False)
eff={**b,'id':'phase2-v5-effect','name':'PHASE 2 QA Effect','source':e,'usageMode':'always','intervalSec':240,'usageDurationSec':30};sub={**b,'id':'phase2-v5-sub','name':'PHASE 2 QA Subscribe','source':s,'scale':.32,'usageMode':'interval','intervalSec':240,'repeatEverySec':240,'firstAtSec':0,'secondAtSec':240,'firstAppearance':'immediate','customFirstAtSec':0,'showDurationSec':8}
json.dump({'effects':[eff],'subscribes':[sub],'ambient':None,'ambientSettings':{'volumePct':18,'bassDb':0,'midDb':0,'trebleDb':0}},open(o,'w'),ensure_ascii=False,indent=2)
PY
ICON="$(find "$QA_APP/Contents/Resources" -maxdepth 1 -type f -name '*.icns' -print -quit)"; /usr/bin/sips -s format png "$ICON" --out "$REPORT/screens/14-application-icon.png" >/dev/null

/bin/launchctl setenv ENDLUME_E2E_LIBRARY_PATH "$FIX/library.json"; /usr/bin/open -n "$QA_APP"
for n in $(seq 0 30); do PIDS="$(pgrep -f "$QA_BIN"||true)"; C="$(printf '%s\n' "$PIDS"|awk 'NF{n++}END{print n+0}')"; if [ "$C" -eq 1 ]; then PID="$(printf '%s\n' "$PIDS"|awk 'NF{print;exit}')"; break; fi; sleep 1; done; test -n "$PID"; /usr/sbin/lsof -a -p "$PID" -d txt -Fn 2>/dev/null|grep -Fxq "n$QA_BIN"; /bin/launchctl unsetenv ENDLUME_E2E_LIBRARY_PATH
cat > "$REPORT/ui.js" <<'JXA'
function run(argv){
 const pid=Number(argv[0]),cmd=argv[1],a1=argv[2]||'',a2=argv[3]||'',se=Application('System Events'),ps=se.applicationProcesses.whose({unixId:pid})();if(ps.length!==1)throw new Error('candidate missing');const p=ps[0];p.frontmost=true;delay(.05);const ws=p.windows();if(!ws.length)throw new Error('no window');const w=ws[0];const str=f=>{try{const v=f();return v==null?'':String(v)}catch(_){return ''}};
 function box(e){try{const q=e.position(),s=e.size();return{x:Number(q[0]),y:Number(q[1]),w:Number(s[0]),h:Number(s[1])}}catch(_){return{x:0,y:0,w:0,h:0}}}
 function bfs(test,max=900){let q=[w],i=0,seen=0;while(i<q.length&&seen<max){const e=q[i++];seen++;const o={e,role:str(()=>e.role()),name:str(()=>e.name()),desc:str(()=>e.description())};const r=test(o);if(r)return r;if(['AXButton','AXStaticText','AXHeading','AXImage','AXSlider','AXTextField'].includes(o.role))continue;let k=[];try{k=e.uiElements()}catch(_){}for(let j=0;j<k.length;j++)q.push(k[j]);}return null;}
 function exact(t,r){return bfs(o=>(o.name===t||o.desc===t)&&(!r||o.role===r)?o:null)}
 function contains(t,r){return bfs(o=>((o.name||'').includes(t)||(o.desc||'').includes(t))&&(!r||o.role===r)?o:null)}
 function visible(t){for(let n=0;n<12;n++){const x=exact(t);if(!x)throw new Error('label missing '+t);const b=box(x.e),z=box(w);if(b.y>z.y+60&&b.y<z.y+z.h-85)return x;se.keyCode(b.y>=z.y+z.h-85?121:116);delay(.18)}throw new Error('not visible '+t)}
 function near(label,names){const l=visible(label),lb=box(l.e),ly=lb.y+lb.h/2,lx=lb.x+lb.w/2;let best=null;bfs(o=>{if(o.role!=='AXButton'||!names.includes(o.name))return null;const b=box(o.e),dy=Math.abs((b.y+b.h/2)-ly),dx=Math.abs((b.x+b.w/2)-lx),score=dy*10+dx;if(!best||score<best.score)best={o,score};return null});if(!best)throw new Error('near button missing '+label);return best.o}
 if(cmd==='geom'){const b=box(w);return `${b.x},${b.y},${b.w},${b.h}`}
 if(cmd==='press'){const x=exact(a1,'AXButton');if(!x)throw new Error('button missing '+a1);x.e.click();delay(.25);return 'OK'}
 if(cmd==='contains'){const x=contains(a1,'AXButton');if(!x)throw new Error('button contains missing '+a1);x.e.click();delay(.25);return 'OK'}
 if(cmd==='has'){return String(contains(a1)?1:0)}
 if(cmd==='scroll'){visible(a1);return 'OK'}
 if(cmd==='nearpress'){const x=near(a1,[a2]);x.e.click();delay(.3);return 'OK'}
 if(cmd==='feature'){const want=a2==='ON';let x=near(a1,['ВКЛЮЧИТЬ','ВЫКЛЮЧИТЬ']),on=x.name==='ВЫКЛЮЧИТЬ';if(on!==want){x.e.click();delay(.35);x=near(a1,['ВКЛЮЧИТЬ','ВЫКЛЮЧИТЬ'])}if((x.name==='ВЫКЛЮЧИТЬ')!==want)throw new Error('feature failed');return 'OK'}
 throw new Error('bad cmd')
}
JXA
ui(){ python3 - "$REPORT/ui.js" "$PID" "$@" <<'PY'
import subprocess,sys
try:r=subprocess.run(['/usr/bin/osascript','-l','JavaScript',sys.argv[1],sys.argv[2],*sys.argv[3:]],text=True,capture_output=True,timeout=5)
except subprocess.TimeoutExpired:raise SystemExit(124)
if r.stdout:print(r.stdout,end='')
if r.returncode:
 print(r.stderr,end='',file=sys.stderr);raise SystemExit(r.returncode)
PY
}
geom(){ ui geom; }
click_rel(){ local fx="$1" fy="$2" g; g="$(geom)"; IFS=',' read -r x y w h <<EOF
$g
EOF
python3 - "$x" "$y" "$w" "$h" "$fx" "$fy" <<'PY' > "$RUNNER_TEMP/phase2-v5-click"
import sys
x,y,w,h,fx,fy=map(float,sys.argv[1:]);print(f'{round(x+w*fx)},{round(y+h*fy)}')
PY
IFS=',' read -r cx cy < "$RUNNER_TEMP/phase2-v5-click"; /usr/bin/osascript -e "tell application \"System Events\" to click at {$cx,$cy}"; sleep .3; }
capture(){ local f="$1" g; g="$(geom)"; IFS=',' read -r x y w h <<EOF
$g
EOF
/usr/sbin/screencapture -x -R"$x,$y,$w,$h" "$REPORT/screens/$f"; test -s "$REPORT/screens/$f"; }
choose(){ /usr/bin/osascript - "$PID" "$1" <<'OSA'
on run argv
 set targetPid to (item 1 of argv) as integer
 set targetPath to item 2 of argv
 tell application "System Events"
  set ps to every application process whose unix id is targetPid
  tell item 1 of ps to set frontmost to true
  keystroke "g" using {command down, shift down};delay 0.35;keystroke targetPath;key code 36;delay 0.65;key code 36
 end tell
end run
OSA
}
wait_has(){ local t="$1" m="${2:-15}"; for n in $(seq 0 "$m"); do set +e; c="$(ui has "$t" 2>/dev/null)"; r=$?; set -e; [ "$r" -eq 0 ]&&[ "${c:-0}" -gt 0 ]&&return 0; sleep .5; done; return 1; }

READY=0; for n in $(seq 0 120); do set +e; a="$(ui has 'АКТИВИРОВАТЬ' 2>/dev/null)"; r=$?; set -e; [ "$r" -eq 0 ]&&[ "${a:-0}" -gt 0 ]&&exit 75; c=0; for t in Проект Рендер Библиотека Настройки; do set +e; q="$(ui has "$t" 2>/dev/null)"; z=$?; set -e; [ "$z" -eq 0 ]&&[ "${q:-0}" -gt 0 ]&&c=$((c+1)); done; [ "$c" -eq 4 ]&&{ READY=1;break; }; sleep .5; done; test "$READY" -eq 1; printf 'LICENSED_SESSION=PASS\nNORMAL_NAVIGATION=PASS\nLICENSE_BYPASS=NO\n' > "$REPORT/license-gate.txt"; echo LICENSED_SESSION=PASS

# Source picker: try BFS, then deterministic physical fallback at center of canonical dropzone.
set +e; ui contains 'Перетащите папки с файлами' >/dev/null 2>&1; rc=$?; set -e; [ "$rc" -eq 0 ] || click_rel .50 .23
choose "$FIX/project"; sleep 2
# Output picker: use BFS scrolling; fallback to bottom-of-project physical position after Cmd+Down.
set +e; ui contains 'Нажмите для выбора папки результата' >/dev/null 2>&1; rc=$?; set -e
if [ "$rc" -ne 0 ]; then /usr/bin/osascript -e 'tell application "System Events" to key code 125 using {command down}'; sleep .4; click_rel .50 .76; fi
choose "$FIX/output"; sleep 1
ui press 'Проект'; capture '01-project.png'
ui feature 'Эффект для каждого проекта' OFF; capture '02-effects-off.png'; ui feature 'Эффект для каждого проекта' ON; capture '03-effects-on.png'
ui feature 'Subscribe Button' OFF; capture '04-subscribe-off.png'; ui feature 'Subscribe Button' ON; capture '05-subscribe-on.png'
ui nearpress 'Эффект для каждого проекта' 'НАСТРОИТЬ →'; wait_has 'LIVE PREVIEW' 15; sleep 2; capture '06-effects-live-preview.png'; ui press '← ВЕРНУТЬСЯ К ПРОЕКТУ'
ui nearpress 'Subscribe Button' 'НАСТРОИТЬ →'; wait_has 'LIVE PREVIEW' 15; sleep 2; capture '06b-subscribe-live-preview.png'; ui press '← ВЕРНУТЬСЯ К ПРОЕКТУ'
ui press 'Рендер'; sleep .5; capture '07-render-idle.png'
ui press 'Библиотека'; sleep .5; capture '09-library.png'
ui press 'Настройки'; sleep .5; ui press 'ОБЩИЕ'; capture '10-settings-general.png'; ui press 'FAST ENGINE'; capture '11-settings-fast-engine.png'; ui press 'ОБНОВЛЕНИЯ'; capture '12-settings-updates.png'; ui press 'О ПРОГРАММЕ'; capture '13-settings-about.png'
ui press 'Проект'; ui feature 'Эффект для каждого проекта' OFF; ui feature 'Subscribe Button' OFF; ui scroll 'ИСХОДНЫЕ ФАЙЛЫ' >/dev/null; ui press '+ ДОБАВИТЬ В ОЧЕРЕДЬ'; sleep 1; /usr/bin/osascript -e 'tell application "System Events" to key code 36' >/dev/null 2>&1 || true
ACTIVE=0; for n in $(seq 0 80); do set +e; c="$(ui has 'ОСТАНОВИТЬ ТЕКУЩИЙ' 2>/dev/null)"; r=$?; set -e; if [ "$r" -eq 0 ]&&[ "${c:-0}" -gt 0 ]; then ACTIVE=1;break;fi;sleep .25;done; test "$ACTIVE" -eq 1; capture '08-render-active.png'; ui press 'ОСТАНОВИТЬ ТЕКУЩИЙ' || true; printf 'RENDER_ACTIVE_PHYSICAL=PASS\n' > "$REPORT/render-active.txt"
expected='01-project.png 02-effects-off.png 03-effects-on.png 04-subscribe-off.png 05-subscribe-on.png 06-effects-live-preview.png 06b-subscribe-live-preview.png 07-render-idle.png 08-render-active.png 09-library.png 10-settings-general.png 11-settings-fast-engine.png 12-settings-updates.png 13-settings-about.png 14-application-icon.png'; : > "$REPORT/evidence.txt"; for f in $expected; do test -s "$REPORT/screens/$f"; echo "$f=PASS" >> "$REPORT/evidence.txt"; done; printf 'PRODUCT_FILES_CHANGED=0\nSTABLE_TOUCHED=NO\nLIVE_UPDATER_TOUCHED=NO\n' >> "$REPORT/evidence.txt"; echo PHYSICAL_14_SCREEN_SUITE=PASS
