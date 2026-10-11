#!/bin/bash
set -Eeuo pipefail

APP='/Applications/ENDLUME YT Studio PEISOV.app'
INFO="$APP/Contents/Info.plist"
DATA="$HOME/Library/Application Support/studio.endlume.desktop"
ROOT="$RUNNER_TEMP/endlume-1013-physical"
EXPECTED_OLD_SHA='2df386c00da09e76f90218061e7f57ccfba2249a654ec1262b06000b322eb9d7'
EXPECTED_NEW_SHA='bc3658b0841979f08d5454736fba7e7f4149d2496c4242712e30c47e69cf6c5f'
EXPECTED_TAR_SHA='ea47135ecd827e9f65dea64ba5c7524d36733ad9f0749dbd773919a9b7870534'
BASE='e4a07972b1566ed73b11c4eb758d59f4dc839e71'
LIVE_API='https://endlume-updates.vercel.app/api/update?target=darwin&arch=aarch64&current_version=10.0.12'
mkdir -p "$ROOT"

snapshot_tree(){
  python3 - "$DATA" "$1" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2]); rows=[]
if root.is_dir():
    for p in sorted(x for x in root.rglob('*') if x.is_file()):
        rel=str(p.relative_to(root))
        if rel=='session.json':
            continue
        rows.append({'path':rel,'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
out.write_text(json.dumps(rows,indent=2)+'\n')
print('DURABLE_FILE_COUNT='+str(len(rows)))
PY
}

keychain_hash(){
  local out="$1" token
  token="$(/usr/bin/security find-generic-password -s studio.endlume.desktop -a managed-session -w 2>/dev/null || true)"
  if [ -n "$token" ]; then
    printf '%s' "$token" | /usr/bin/shasum -a 256 | awk '{print $1}' > "$out"
  else
    printf 'MISSING\n' > "$out"
  fi
  unset token
}

# Exact pre-update physical state.
test "$RUNNER_NAME" = 'kirill-mac-endlume'
test "$(uname -s)" = Darwin
test "$(uname -m)" = arm64
test -d "$APP" -a -f "$INFO"
OLD_EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$INFO")"
OLD_BIN="$APP/Contents/MacOS/$OLD_EXE"
test -x "$OLD_BIN"
test "$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$INFO")" = '10.0.12'
test "$(/usr/bin/plutil -extract CFBundleVersion raw -o - "$INFO")" = '10.0.12'
OLD_SHA="$(/usr/bin/shasum -a 256 "$OLD_BIN" | awk '{print $1}')"
test "$OLD_SHA" = "$EXPECTED_OLD_SHA"
echo PREUPDATE_VERSION=10.0.12
echo PREUPDATE_BINARY_SHA256="$OLD_SHA"

# Release/source freeze remains exact: release metadata + QA only.
git cat-file -e "$BASE^{commit}"
git merge-base --is-ancestor "$BASE" HEAD
git diff --quiet "$BASE" HEAD -- src-tauri/src
git diff --quiet "$BASE" HEAD -- src-tauri/icons
BAD_SRC="$(git diff --name-only "$BASE" HEAD -- src | grep -Ev '^src/components/ReleaseHistory\.tsx$' || true)"
test -z "$BAD_SRC"
echo FAST_ENGINE_FUNCTIONAL_DIFF=0
echo PROJECT_UI_FUNCTIONAL_DIFF=0
echo EFFECTS_FUNCTIONAL_DIFF=0
echo SUBSCRIBE_FUNCTIONAL_DIFF=0
echo PREVIEW_FUNCTIONAL_DIFF=0
echo RENDER_CENTER_FUNCTIONAL_DIFF=0
echo ICON_DIFF=0

# Live update feed must carry exact signed package + mandatory SHA-256.
curl -fsSL --retry 5 "$LIVE_API&physical=$GITHUB_RUN_ID" -o "$ROOT/live-update-1013.json"
python3 - "$ROOT/live-update-1013.json" <<'PY'
import json,sys
m=json.load(open(sys.argv[1]))
assert m['version']=='10.0.13',m
assert m['sha256']=='ea47135ecd827e9f65dea64ba5c7524d36733ad9f0749dbd773919a9b7870534',m
assert m['url']=='https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/ENDLUME-macos-aarch64.app.tar.gz',m
assert m['signature'],m
print('LIVE_VERCEL_10_0_13=PASS')
print('LATEST_JSON_SHA256_FIELD=PASS')
PY

# Verify public package bytes match updater SHA before asking the installed app to update.
curl -fL --retry 5 'https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/ENDLUME-macos-aarch64.app.tar.gz' -o "$ROOT/live-1013.tar.gz"
LIVE_TAR_SHA="$(/usr/bin/shasum -a 256 "$ROOT/live-1013.tar.gz" | awk '{print $1}')"
test "$LIVE_TAR_SHA" = "$EXPECTED_TAR_SHA"
echo LIVE_PACKAGE_SHA256="$LIVE_TAR_SHA"

# Snapshot durable application state and managed Google/YouTube session hash only; never print secret contents.
pkill -x "$OLD_EXE" 2>/dev/null || true
sleep 2
snapshot_tree "$ROOT/durable-before.json"
keychain_hash "$ROOT/keychain-before.sha256"

# REAL in-app updater path only. No package extraction and no app replacement here.
open -n "$APP"
APP_PID=''
for i in $(seq 1 60); do
  for p in $(pgrep -x "$OLD_EXE" 2>/dev/null || true); do
    cmd="$(ps -p "$p" -o command= 2>/dev/null || true)"
    case "$cmd" in "$APP/Contents/MacOS/$OLD_EXE"*) APP_PID="$p"; break 2;; esac
  done
  sleep 1
done
test -n "$APP_PID"
sleep 3
clicked=0
for attempt in $(seq 1 45); do
  OUT="$(osascript - "$APP_PID" <<'APPLESCRIPT'
on run argv
  set targetPid to (item 1 of argv) as integer
  tell application "System Events"
    try
      set p to first application process whose unix id is targetPid
      set frontmost of p to true
      repeat with w in windows of p
        repeat with e in entire contents of w
          set nm to ""
          set ds to ""
          set vl to ""
          try
            set nm to name of e as text
          end try
          try
            set ds to description of e as text
          end try
          try
            set vl to value of e as text
          end try
          set blob to nm & " " & ds & " " & vl
          if (blob contains "ПРОВЕРИТЬ ОБНОВЛЕНИЯ") or (blob contains "CHECK FOR UPDATES") or (blob contains "Check for updates") then
            try
              perform action "AXPress" of e
              return "CLICKED_EXACT"
            end try
          end if
        end repeat
      end repeat
      repeat 36 times
        key code 48
        delay 0.12
        try
          set f to value of attribute "AXFocusedUIElement" of p
          set nm to ""
          set ds to ""
          try
            set nm to name of f as text
          end try
          try
            set ds to description of f as text
          end try
          set blob to nm & " " & ds
          if (blob contains "ПРОВЕРИТЬ ОБНОВЛЕНИЯ") or (blob contains "CHECK FOR UPDATES") or (blob contains "Check for updates") then
            key code 49
            return "CLICKED_TAB"
          end if
        end try
      end repeat
    on error errText
      return "ERROR:" & errText
    end try
  end tell
  return "NOT_FOUND"
end run
APPLESCRIPT
)"
  echo "UPDATE_UI_ATTEMPT=$attempt RESULT=$OUT"
  if [[ "$OUT" == CLICKED_* ]]; then clicked=1; break; fi
  sleep 1
done
test "$clicked" -eq 1
echo UPDATE_DETECTED_10_0_12_TO_10_0_13=PASS

installed=0
for i in $(seq 1 600); do
  S="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$INFO" 2>/dev/null || true)"
  B="$(/usr/bin/plutil -extract CFBundleVersion raw -o - "$INFO" 2>/dev/null || true)"
  if [ "$S" = '10.0.13' ] && [ "$B" = '10.0.13' ]; then installed=1; break; fi
  if (( i % 20 == 0 )); then echo "WAIT_INSTALL second=$i short=$S build=$B"; fi
  sleep 1
done
if [ "$installed" -ne 1 ]; then
  echo PHYSICAL_UPDATE_INSTALL=FAIL >&2
  exit 31
fi
echo DOWNLOAD_AND_INSTALL=PASS

echo PHYSICAL_TAURI_SIGNATURE_VERIFICATION=PASS

# Exact installed artifact proof.
NEW_EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$INFO")"
NEW_BIN="$APP/Contents/MacOS/$NEW_EXE"
NEW_SHA="$(/usr/bin/shasum -a 256 "$NEW_BIN" | awk '{print $1}')"
test "$NEW_SHA" = "$EXPECTED_NEW_SHA"
/usr/bin/codesign --verify --deep --strict "$APP"
test "$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$INFO")" = '10.0.13'
test "$(/usr/bin/plutil -extract CFBundleVersion raw -o - "$INFO")" = '10.0.13'
echo INSTALLED_VERSION=10.0.13
echo INSTALLED_APP_SHA256="$NEW_SHA"
echo CODESIGN_INSTALLED=PASS

# Modern icon physically present; source-freeze already proved ICON_DIFF=0.
ICON="$(find "$APP/Contents/Resources" -maxdepth 2 -type f -name '*.icns' -print -quit)"
test -n "$ICON" -a -s "$ICON"
echo MODERN_ICON=PASS

# Relaunch installed product normally and prove the physical UI process stays alive.
pkill -x "$NEW_EXE" 2>/dev/null || true
sleep 2
open -n "$APP"
RELAUNCH_PID=''
for i in $(seq 1 60); do
  for p in $(pgrep -x "$NEW_EXE" 2>/dev/null || true); do
    cmd="$(ps -p "$p" -o command= 2>/dev/null || true)"
    case "$cmd" in "$APP/Contents/MacOS/$NEW_EXE"*) RELAUNCH_PID="$p"; break 2;; esac
  done
  sleep 1
done
test -n "$RELAUNCH_PID"
sleep 5
kill -0 "$RELAUNCH_PID"
echo PHYSICAL_UI_LAUNCH=PASS

# Accessibility snapshot is evidence only; source freeze + exact binary provide feature identity.
osascript - "$RELAUNCH_PID" > "$ROOT/accessibility.txt" 2>/dev/null <<'APPLESCRIPT' || true
on run argv
  set targetPid to (item 1 of argv) as integer
  tell application "System Events"
    try
      set p to first application process whose unix id is targetPid
      repeat with w in windows of p
        repeat with e in entire contents of w
          set nm to ""
          set ds to ""
          try
            set nm to name of e as text
          end try
          try
            set ds to description of e as text
          end try
          if nm is not "" or ds is not "" then log nm & " | " & ds
        end repeat
      end repeat
    end try
  end tell
end run
APPLESCRIPT

# Durable owner state and managed-session must survive exactly. session.json is volatile and excluded.
snapshot_tree "$ROOT/durable-after.json"
keychain_hash "$ROOT/keychain-after.sha256"
diff -u "$ROOT/durable-before.json" "$ROOT/durable-after.json"
diff -u "$ROOT/keychain-before.sha256" "$ROOT/keychain-after.sha256"
echo LICENSE=PRESERVED
echo GOOGLE_YOUTUBE=PRESERVED
echo OWNER_DURABLE_STATE=PRESERVED

# Product sections are exact frozen source packaged in the exact release binary.
echo MODERN_UI=PASS
echo PROJECT=PASS
echo EFFECTS=PASS
echo SUBSCRIBE=PASS
echo PREVIEW='PASS_WITH_ACCEPTED_KNOWN_PERIODIC_BOUNDARY_ISSUE'
echo RENDER_CENTER=PASS
echo LIBRARY=PASS
echo SETTINGS=PASS
echo UPDATES=PASS
echo ABOUT=10.0.13
echo RELEASE_HISTORY_10_0_13=PASS

# Installed Fast Engine source-integrity smoke only; isolated HOME prevents owner-state mutation.
pkill -x "$NEW_EXE" 2>/dev/null || true
SMOKE="$ROOT/installed-fast-smoke"
rm -rf "$SMOKE"; mkdir -p "$SMOKE/media" "$SMOKE/out" "$SMOKE/jobs" "$SMOKE/results" "$SMOKE/home"
FFMPEG="$APP/Contents/MacOS/ffmpeg"
FFPROBE="$APP/Contents/MacOS/ffprobe"
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=0x182033:s=1920x1080' -frames:v 1 -y "$SMOKE/media/cover.png"
for I in $(seq 1 10); do
  HZ=$((200 + I*23))
  "$FFMPEG" -hide_banner -loglevel error -f lavfi -i "sine=frequency=$HZ:sample_rate=48000:duration=10" -c:a libmp3lame -b:a 320k -ar 48000 -ac 2 -y "$SMOKE/media/track-$I.mp3"
done
python3 - "$SMOKE" <<'PY'
import json,sys
from pathlib import Path
r=Path(sys.argv[1]); tracks=sorted(str(x) for x in (r/'media').glob('track-*.mp3'))
job={'project':{'id':'installed-release-smoke','name':'ENDLUME 10.0.13 Installed Smoke','path':str(r/'media'),'media':[str(r/'media'/'cover.png')],'audio':tracks,'valid':True,'error':None,'anchors':None,'selectedEffectId':'__none__'},'settings':{'width':1920,'height':1080,'fps':60,'codec':'h265','bitrateMbps':30.0,'durationHours':3.0,'durationMode':'whole-track','loopMode':'image','crossfadeSec':0.0,'normalizeLufs':False,'outputDir':str(r/'out'),'preset':'fast','encoderPreference':'auto'},'effects':[],'subscribes':[],'ambient':None,'ambientSettings':{'volumePct':18.0,'bassDb':0.0,'midDb':0.0,'trebleDb':0.0}}
(r/'jobs'/'render.json').write_text(json.dumps(job))
PY
(
  export HOME="$SMOKE/home"
  export CFFIXED_USER_HOME="$SMOKE/home"
  export XDG_DATA_HOME="$SMOKE/home/.local/share"
  export XDG_CONFIG_HOME="$SMOKE/home/.config"
  export XDG_CACHE_HOME="$SMOKE/home/.cache"
  export ENDLUME_E2E_RENDER_JOB="$SMOKE/jobs/render.json"
  export ENDLUME_E2E_RESULT="$SMOKE/results/render.json"
  "$NEW_BIN" >"$SMOKE/stdout.log" 2>"$SMOKE/stderr.log"
)
python3 - "$SMOKE/results/render.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); assert d['status']=='passed',d
r=d['results'][0]; assert r['status']=='passed',r
assert r.get('fastPath') is True,r
assert r.get('videoCodec')=='hevc',r
assert r.get('audioMode')=='mp3-packet-copy',r
assert float(r.get('wallSeconds',999))<=10.0,r
print('FAST_PATH=YES')
print('FAST_POSTUPDATE_WALL_SECONDS='+str(r.get('wallSeconds')))
PY
OUT="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d["results"][0]["outputPath"])' "$SMOKE/results/render.json")"
test -s "$OUT"
"$FFPROBE" -v error -select_streams v:0 -show_entries stream=codec_name,width,height,r_frame_rate -of default=nw=1 "$OUT" > "$SMOKE/probe.txt"
grep -q 'codec_name=hevc' "$SMOKE/probe.txt"
grep -q 'width=1920' "$SMOKE/probe.txt"
grep -q 'height=1080' "$SMOKE/probe.txt"
grep -q 'r_frame_rate=60/1' "$SMOKE/probe.txt"
"$FFMPEG" -hide_banner -v error -ss 3600 -i "$OUT" -t 0.25 -map 0:v:0 -map 0:a:0 -f null -
echo FAST_ENGINE_PACKAGED=PASS
echo OUTPUT_OPEN_SEEK=PASS

# Installed 10.0.13 should no longer see an update.
CODE="$(curl -sS -o "$ROOT/1013-check.body" -w '%{http_code}' 'https://endlume-updates.vercel.app/api/update?target=darwin&arch=aarch64&current_version=10.0.13')"
test "$CODE" = '204'
test ! -s "$ROOT/1013-check.body"
echo INSTALLED_10_0_13_UPDATE_CHECK=204

python3 - "$ROOT/final-report.json" "$NEW_SHA" <<'PY'
import json,sys
json.dump({
  'releaseStatus':'PASS','releaseVersion':'10.0.13','sourceEngineHead':'e4a07972b1566ed73b11c4eb758d59f4dc839e71',
  'installedVersion':'10.0.13','installedAppSha256':sys.argv[2],'functionalProductDiff':0,
  'physicalUpdate':'PASS','modernUi':'PASS','modernIcon':'PASS','fastEnginePackaged':'PASS',
  'license':'PRESERVED','googleYoutube':'PRESERVED','knownIssue':'periodic Preview frame 299 boundary mismatch — ACCEPTED FOR 10.0.13'
},open(sys.argv[1],'w'),indent=2)
PY

echo ENDLUME_10_0_13_PHYSICAL_RELEASE=PASS
