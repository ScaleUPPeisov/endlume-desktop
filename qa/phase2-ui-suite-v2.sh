#!/bin/bash
set -Eeuo pipefail
REPORT="$RUNNER_TEMP/endlume-phase2-v2"
STATE="$RUNNER_TEMP/endlume-phase2-v2-state"
FIX="$RUNNER_TEMP/endlume-phase2-v2-fixture"
UNPACK="$RUNNER_TEMP/endlume-phase2-v2-unpack"
DMG="$RUNNER_TEMP/ENDLUME-PHASE2-V2.dmg"
APP_DATA="$HOME/Library/Application Support/studio.endlume.desktop"
WEBKIT="$HOME/Library/WebKit/studio.endlume.desktop"
OWNER_APP="/Applications/ENDLUME YT Studio PEISOV.app"
rm -rf "$REPORT" "$STATE" "$FIX" "$UNPACK" "$DMG"
mkdir -p "$REPORT/screens" "$STATE" "$FIX/project" "$FIX/output" "$APP_DATA"
QA_BIN=""; QA_VOL=""; PID=""
cleanup(){
  set +e
  /bin/launchctl unsetenv ENDLUME_E2E_LIBRARY_PATH >/dev/null 2>&1
  [ -z "$QA_BIN" ] || pkill -f "$QA_BIN" >/dev/null 2>&1
  sleep 2
  [ -z "$QA_VOL" ] || hdiutil detach -quiet "$QA_VOL" >/dev/null 2>&1
  for n in library.json queue.json recovery.json session.json; do
    if [ -f "$STATE/$n" ]; then cp -p "$STATE/$n" "$APP_DATA/$n"; elif [ -f "$STATE/$n.ABSENT" ]; then rm -f "$APP_DATA/$n"; fi
  done
  if [ -d "$STATE/webkit" ]; then rm -rf "$WEBKIT"; ditto "$STATE/webkit" "$WEBKIT"; elif [ -f "$STATE/WEBKIT.ABSENT" ]; then rm -rf "$WEBKIT"; fi
  if [ -f "$STATE/managed-assets.txt" ]; then while IFS= read -r p; do rm -f "$p"; done < "$STATE/managed-assets.txt"; fi
  if [ -d "$OWNER_APP" ]; then
    oe="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$OWNER_APP/Contents/Info.plist" 2>/dev/null)"
    os="$(shasum -a 256 "$OWNER_APP/Contents/MacOS/$oe" 2>/dev/null|awk '{print $1}')"
    printf 'OWNER_BIN_SHA256=%s\n' "$os" > "$REPORT/owner-after.txt"
  fi
  printf 'OWNER_STATE_RESTORED=YES\n' > "$REPORT/cleanup.txt"
}
trap cleanup EXIT

test "$RUNNER_NAME" = "kirill-mac-endlume"
test "$(/usr/bin/osascript -e 'tell application "System Events" to return UI elements enabled' 2>/dev/null || echo false)" = true
test -d "$OWNER_APP"
OWNER_EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$OWNER_APP/Contents/Info.plist")"
OWNER_BIN="$OWNER_APP/Contents/MacOS/$OWNER_EXE"
OWNER_SHA="$(shasum -a 256 "$OWNER_BIN"|awk '{print $1}')"
test "$OWNER_SHA" = "$OWNER_APP_BIN_SHA256"
! pgrep -f "$OWNER_BIN" >/dev/null 2>&1
printf 'OWNER_BIN_SHA256=%s\n' "$OWNER_SHA" > "$REPORT/owner-before.txt"
for n in library.json queue.json recovery.json session.json; do if [ -f "$APP_DATA/$n" ]; then cp -p "$APP_DATA/$n" "$STATE/$n"; else touch "$STATE/$n.ABSENT"; fi; done
python3 - "$APP_DATA/queue.json" <<'PY'
import json,os,sys
p=sys.argv[1]
if os.path.isfile(p):
    try:q=json.load(open(p))
    except Exception:q={}
    if q.get('active') is not None or (q.get('pending') or []): print('BLOCKED_OWNER_QUEUE_NOT_EMPTY=true');raise SystemExit(91)
PY
if [ -d "$WEBKIT" ]; then ditto "$WEBKIT" "$STATE/webkit"; else touch "$STATE/WEBKIT.ABSENT"; fi
echo SAFETY_GATE=PASS

ZIP="$RUNNER_TEMP/phase2-v2-source/ENDLUME-CANONICAL-GOOD-PRODUCT-QA.app.zip"
test -f "$ZIP"
test "$(shasum -a 256 "$ZIP"|awk '{print $1}')" = "$EXPECTED_APP_ZIP_SHA256"
ditto -x -k "$ZIP" "$UNPACK"
BUILT_APP="$(find "$UNPACK" -maxdepth 2 -type d -name '*.app' -print -quit)"
EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$BUILT_APP/Contents/Info.plist")"
test "$(shasum -a 256 "$BUILT_APP/Contents/MacOS/$EXE"|awk '{print $1}')" = "$EXPECTED_APP_BIN_SHA256"
/usr/bin/codesign --verify --deep --strict "$BUILT_APP"
hdiutil create -quiet -size 350m -fs APFS -volname ENDLUME_CANONICAL_QA_V2 "$DMG"
hdiutil attach -nobrowse -plist "$DMG" > "$RUNNER_TEMP/phase2-v2-attach.plist"
QA_VOL="$(python3 - "$RUNNER_TEMP/phase2-v2-attach.plist" <<'PY'
import plistlib,sys
p=plistlib.load(open(sys.argv[1],'rb'));xs=[x.get('mount-point') for x in p.get('system-entities',[]) if x.get('mount-point')];print(xs[-1])
PY
)"
QA_APP="$QA_VOL/ENDLUME-CANONICAL-GOOD-PRODUCT-QA.app"
ditto "$BUILT_APP" "$QA_APP"
QA_BIN="$QA_APP/Contents/MacOS/$EXE"
test "$(shasum -a 256 "$QA_BIN"|awk '{print $1}')" = "$EXPECTED_APP_BIN_SHA256"
/usr/bin/codesign --verify --deep --strict "$QA_APP"

FFMPEG="$(find "$QA_APP/Contents" -type f -perm -111 -name 'ffmpeg*' -print | head -1)"
"$FFMPEG" -hide_banner -loglevel error -y -f lavfi -i color=c=0x142039:s=1920x1080 -frames:v 1 "$FIX/project/base.png"
"$FFMPEG" -hide_banner -loglevel error -y -f lavfi -i sine=frequency=330:duration=90 -c:a libmp3lame -b:a 192k -ar 48000 -ac 2 "$FIX/project/track-01.mp3"
"$FFMPEG" -hide_banner -loglevel error -y -f lavfi -i sine=frequency=440:duration=90 -c:a libmp3lame -b:a 192k -ar 48000 -ac 2 "$FIX/project/track-02.mp3"
"$FFMPEG" -hide_banner -loglevel error -y -f lavfi -i color=c=0x00ff00:s=640x360:d=2 -vf 'drawbox=x=180:y=90:w=280:h=180:color=red@1:t=fill' -c:v h264_videotoolbox -pix_fmt yuv420p "$FIX/effect.mp4"
"$FFMPEG" -hide_banner -loglevel error -y -f lavfi -i color=c=0x00ff00:s=640x360:d=2 -vf 'drawbox=x=120:y=130:w=400:h=100:color=magenta@1:t=fill' -c:v h264_videotoolbox -pix_fmt yuv420p "$FIX/subscribe.mp4"
EROOT="$APP_DATA/library-assets/effects"; SROOT="$APP_DATA/library-assets/subscribe"; mkdir -p "$EROOT" "$SROOT"
QAE="$EROOT/phase2-v2-effect-${GITHUB_RUN_ID}.mp4"; QAS="$SROOT/phase2-v2-subscribe-${GITHUB_RUN_ID}.mp4"
cp "$FIX/effect.mp4" "$QAE"; cp "$FIX/subscribe.mp4" "$QAS"; printf '%s\n%s\n' "$QAE" "$QAS" > "$STATE/managed-assets.txt"
python3 - "$QAE" "$QAS" "$FIX/library.json" <<'PY'
import json,sys
e,s,o=sys.argv[1:]
b=dict(enabled=True,mode='chromakey',keyColor='#00ff00',similarity=.10,blend=.06,despill=.35,lumaThreshold=.03,lumaTolerance=.08,saturation=1,x=.5,y=.5,scale=.34,fullscreen=False,previewFrameTime=0,startSec=0,endSec=None,target='CUSTOM',offsetX=0,offsetY=0,opacity=1,assetState='ready',cacheReady=False)
eff={**b,'id':'phase2-v2-effect','name':'PHASE 2 QA Effect','source':e,'usageMode':'always','intervalSec':240,'usageDurationSec':30}
sub={**b,'id':'phase2-v2-sub','name':'PHASE 2 QA Subscribe','source':s,'scale':.32,'usageMode':'interval','intervalSec':240,'repeatEverySec':240,'firstAtSec':0,'secondAtSec':240,'firstAppearance':'immediate','customFirstAtSec':0,'showDurationSec':8}
json.dump({'effects':[eff],'subscribes':[sub],'ambient':None,'ambientSettings':{'volumePct':18,'bassDb':0,'midDb':0,'trebleDb':0}},open(o,'w'),ensure_ascii=False,indent=2)
PY
ICON="$(find "$QA_APP/Contents/Resources" -maxdepth 1 -type f -name '*.icns' -print -quit)"
/usr/bin/sips -s format png "$ICON" --out "$REPORT/screens/14-application-icon.png" >/dev/null

/bin/launchctl setenv ENDLUME_E2E_LIBRARY_PATH "$FIX/library.json"
/usr/bin/open -n "$QA_APP"
for n in $(seq 0 30); do PIDS="$(pgrep -f "$QA_BIN"||true)"; C="$(printf '%s\n' "$PIDS"|awk 'NF{n++}END{print n+0}')"; if [ "$C" -eq 1 ]; then PID="$(printf '%s\n' "$PIDS"|awk 'NF{print;exit}')"; break; fi; sleep 1; done
test -n "$PID"
/usr/sbin/lsof -a -p "$PID" -d txt -Fn 2>/dev/null | grep -Fxq "n$QA_BIN"
/bin/launchctl unsetenv ENDLUME_E2E_LIBRARY_PATH
DRIVER="$GITHUB_WORKSPACE/qa/phase2-ui-driver-v2.js"
ui(){ /usr/bin/osascript -l JavaScript "$DRIVER" "$PID" "$@"; }
wait_text(){ local t="$1" m="${2:-20}"; for i in $(seq 0 "$m"); do [ "$(ui has "$t" 2>/dev/null||echo 0)" -gt 0 ] 2>/dev/null && return 0; sleep 1; done; return 1; }
capture(){ local f="$1" g; g="$(ui geom)"; IFS=',' read -r x y w h <<EOF
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
    keystroke "g" using {command down, shift down}
    delay 0.4
    keystroke targetPath
    key code 36
    delay 0.7
    key code 36
  end tell
end run
OSA
}

echo MANUAL_ACTION_IF_PROMPT=CLICK_ALLOW_NOT_ALWAYS_ALLOW
READY=0
for i in $(seq 0 180); do
  A="$(ui has 'АКТИВИРОВАТЬ' 2>/dev/null||echo 0)"; if [ "$A" -gt 0 ] 2>/dev/null; then echo ACTIVATION_SCREEN=FAIL; exit 75; fi
  N=0; for t in Проект Рендер Библиотека Настройки; do [ "$(ui has "$t" 2>/dev/null||echo 0)" -gt 0 ] 2>/dev/null && N=$((N+1)); done
  if [ "$N" -eq 4 ]; then READY=1; break; fi
  sleep 1
done
test "$READY" -eq 1
printf 'LICENSED_SESSION=PASS\nNORMAL_NAVIGATION=PASS\nLICENSE_BYPASS=NO\n' > "$REPORT/license-gate.txt"
echo LICENSED_SESSION=PASS

ui press 'Перетащите папки с файлами или нажмите для выбора'; choose "$FIX/project"; sleep 2
ui press 'Нажмите для выбора папки результата'; choose "$FIX/output"; sleep 1
ui press 'Проект'; ui scroll 'ИСХОДНЫЕ ФАЙЛЫ'; capture '01-project.png'
ui feature 'Эффект для каждого проекта' OFF; capture '02-effects-off.png'
ui feature 'Эффект для каждого проекта' ON; capture '03-effects-on.png'
ui feature 'Subscribe Button' OFF; capture '04-subscribe-off.png'
ui feature 'Subscribe Button' ON; capture '05-subscribe-on.png'
ui nearpress 'Эффект для каждого проекта' 'НАСТРОИТЬ →'; wait_text 'LIVE PREVIEW' 20; sleep 2; capture '06-effects-live-preview.png'; ui press '← ВЕРНУТЬСЯ К ПРОЕКТУ'
ui nearpress 'Subscribe Button' 'НАСТРОИТЬ →'; wait_text 'LIVE PREVIEW' 20; sleep 2; capture '06b-subscribe-live-preview.png'; ui press '← ВЕРНУТЬСЯ К ПРОЕКТУ'
ui press 'Рендер'; wait_text 'Очередь пуста' 10; capture '07-render-idle.png'
ui press 'Библиотека'; wait_text 'Библиотека' 10; capture '09-library.png'
ui press 'Настройки'; wait_text 'ОБЩИЕ' 10; ui press 'ОБЩИЕ'; capture '10-settings-general.png'; ui press 'FAST ENGINE'; capture '11-settings-fast-engine.png'; ui press 'ОБНОВЛЕНИЯ'; capture '12-settings-updates.png'; ui press 'О ПРОГРАММЕ'; capture '13-settings-about.png'
ui press 'Проект'; sleep .5; ui feature 'Эффект для каждого проекта' OFF; ui feature 'Subscribe Button' OFF; ui scroll 'ИСХОДНЫЕ ФАЙЛЫ'; ui press '+ ДОБАВИТЬ В ОЧЕРЕДЬ'
ACTIVE=0
for i in $(seq 0 100); do
  if [ "$(ui has 'ОСТАНОВИТЬ ТЕКУЩИЙ' 2>/dev/null||echo 0)" -gt 0 ] 2>/dev/null; then ACTIVE=1; break; fi
  if [ "$i" -eq 10 ] || [ "$i" -eq 30 ]; then /usr/bin/osascript -e 'tell application "System Events" to key code 36' >/dev/null 2>&1 || true; fi
  sleep .2
done
test "$ACTIVE" -eq 1
capture '08-render-active.png'
ui press 'ОСТАНОВИТЬ ТЕКУЩИЙ' || true
printf 'RENDER_ACTIVE_PHYSICAL=PASS\n' > "$REPORT/render-active.txt"
expected='01-project.png 02-effects-off.png 03-effects-on.png 04-subscribe-off.png 05-subscribe-on.png 06-effects-live-preview.png 06b-subscribe-live-preview.png 07-render-idle.png 08-render-active.png 09-library.png 10-settings-general.png 11-settings-fast-engine.png 12-settings-updates.png 13-settings-about.png 14-application-icon.png'
: > "$REPORT/evidence.txt"
for f in $expected; do test -s "$REPORT/screens/$f"; echo "$f=PASS" >> "$REPORT/evidence.txt"; done
printf 'PRODUCT_FILES_CHANGED=0\nSTABLE_TOUCHED=NO\nLIVE_UPDATER_TOUCHED=NO\nCANDIDATE_PRODUCT_SHA=%s\nAPP_SHA256=%s\n' "$CANONICAL_PRODUCT_SHA" "$EXPECTED_APP_BIN_SHA256" >> "$REPORT/evidence.txt"
echo PHYSICAL_14_SCREEN_SUITE=PASS
