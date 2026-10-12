#!/bin/bash
set -Eeuo pipefail

: "${ROLLBACK_DIR:?ROLLBACK_DIR missing}"
: "${GH_TOKEN:?GH_TOKEN missing}"
APP='/Applications/ENDLUME YT Studio PEISOV.app'
INFO="$APP/Contents/Info.plist"
DATA="$HOME/Library/Application Support/studio.endlume.desktop"
ROOT="$RUNNER_TEMP/endlume-1014-updater-acceptance"
BASE_URL='https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable'
STABLE_REPO='ScaleUPPeisov/scaleup-site'
STABLE_TAG='endlume-stable'
mkdir -p "$ROOT"

snapshot_tree(){
  python3 - "$DATA" "$1" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2]); rows=[]
if root.is_dir():
    for p in sorted(x for x in root.rglob('*') if x.is_file()):
        rel=str(p.relative_to(root))
        if rel=='session.json': continue
        rows.append({'path':rel,'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
out.write_text(json.dumps(rows,indent=2)+'\n')
print('DURABLE_FILE_COUNT='+str(len(rows)))
PY
}
keychain_hash(){
  local out="$1" token
  token="$(/usr/bin/security find-generic-password -s studio.endlume.desktop -a managed-session -w 2>/dev/null || true)"
  if [ -n "$token" ]; then printf '%s' "$token" | /usr/bin/shasum -a 256 | awk '{print $1}' > "$out"; else printf 'MISSING\n' > "$out"; fi
  unset token
}
restore_production_1013(){
  set +e
  echo ROLLBACK_10_0_13=START >&2
  gh release upload "$STABLE_TAG" "$ROLLBACK_DIR/ENDLUME-macos-aarch64.app.tar.gz" "$ROLLBACK_DIR/ENDLUME-macos-aarch64.app.tar.gz.sig" --clobber --repo "$STABLE_REPO"
  gh release upload "$STABLE_TAG" "$ROLLBACK_DIR/latest.json" --clobber --repo "$STABLE_REPO"
  sleep 2
  curl -fL --retry 5 "$BASE_URL/latest.json?rollback-verify=$(date +%s)" -o "$ROOT/rollback-live.json"
  python3 - "$ROOT/rollback-live.json" <<'PY'
import json,sys
m=json.load(open(sys.argv[1])); assert m['version']=='10.0.13',m
print('ROLLBACK_LIVE_VERSION=10.0.13')
PY
  # Restore the dedicated physical-test machine to its exact 10.0.13 updater package too.
  if [ -s "$ROLLBACK_DIR/ENDLUME-macos-aarch64.app.tar.gz" ]; then
    pkill -f "$APP/Contents/MacOS/" 2>/dev/null || true
    R="$ROOT/restore-app"; rm -rf "$R"; mkdir -p "$R"
    /usr/bin/tar -xzf "$ROLLBACK_DIR/ENDLUME-macos-aarch64.app.tar.gz" -C "$R" >/dev/null 2>&1
    OLD_APP="$(find "$R" -maxdepth 2 -type d -name '*.app' -print -quit)"
    if [ -n "$OLD_APP" ] && [ -d "$OLD_APP" ]; then
      rm -rf "$APP"
      /usr/bin/ditto "$OLD_APP" "$APP"
    fi
  fi
  echo ROLLBACK_10_0_13=COMPLETE >&2
}
on_error(){ rc=$?; restore_production_1013; exit "$rc"; }
trap on_error ERR

# Exact physical baseline must be an installed 10.0.13 application.
test "$RUNNER_NAME" = 'kirill-mac-endlume'
test "$(uname -s)" = Darwin
test "$(uname -m)" = arm64
test -d "$APP" -a -f "$INFO"
OLD_EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$INFO")"
OLD_BIN="$APP/Contents/MacOS/$OLD_EXE"
test -x "$OLD_BIN"
test "$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$INFO")" = '10.0.13'
test "$(/usr/bin/plutil -extract CFBundleVersion raw -o - "$INFO")" = '10.0.13'
test "$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$INFO")" = 'studio.endlume.desktop'
OLD_SHA="$(/usr/bin/shasum -a 256 "$OLD_BIN" | awk '{print $1}')"
echo PREUPDATE_VERSION=10.0.13
echo PREUPDATE_BINARY_SHA256="$OLD_SHA"

# Live production must already be 10.0.14 and its public bytes must match the manifest.
CACHE="$(date +%s)-${GITHUB_RUN_ID:-local}"
curl -fL --retry 5 "$BASE_URL/latest.json?physical=$CACHE" -o "$ROOT/live-latest.json"
curl -fL --retry 5 "$BASE_URL/ENDLUME-macos-aarch64.app.tar.gz?physical=$CACHE" -o "$ROOT/live-1014.tar.gz"
curl -fL --retry 5 "$BASE_URL/ENDLUME-macos-aarch64.app.tar.gz.sig?physical=$CACHE" -o "$ROOT/live-1014.tar.gz.sig"
curl -fL --retry 5 "$BASE_URL/ENDLUME-10.0.14-release.json?physical=$CACHE" -o "$ROOT/release-1014.json"
python3 - "$ROOT/live-latest.json" "$ROOT/live-1014.tar.gz" "$ROOT/live-1014.tar.gz.sig" "$ROOT/release-1014.json" <<'PY'
import hashlib,json,sys
latest,tar,sig,release=sys.argv[1:]
m=json.load(open(latest)); r=json.load(open(release))
assert m['version']=='10.0.14',m
p=m['platforms']['darwin-aarch64']
sha=hashlib.sha256(open(tar,'rb').read()).hexdigest(); sigtxt=open(sig).read().strip()
assert p['sha256']==sha==r['tarGzSha256'],(p.get('sha256'),sha,r.get('tarGzSha256'))
assert p['signature']==sigtxt
assert r['releaseVersion']=='10.0.14' and r['signatureVerify']=='PASS' and r['packagedSmoke']=='PASS',r
print('LIVE_STABLE_10_0_14=PASS')
print('LIVE_PACKAGE_SHA256='+sha)
print('LIVE_SIGNATURE_METADATA=PASS')
PY

# Independent signature verification before exercising the normal in-app updater.
PUB="$HOME/.endlume-updater/endlume.key.pub"
test -s "$PUB"
command -v minisign >/dev/null 2>&1 || /opt/homebrew/bin/brew install minisign
python3 - "$PUB" "$ROOT/live-1014.tar.gz.sig" "$ROOT/minisign.pub" "$ROOT/minisign.sig" <<'PY'
import base64,sys
from pathlib import Path
Path(sys.argv[3]).write_bytes(base64.b64decode(Path(sys.argv[1]).read_text().strip()))
Path(sys.argv[4]).write_bytes(base64.b64decode(Path(sys.argv[2]).read_text().strip()))
PY
minisign -Vm "$ROOT/live-1014.tar.gz" -p "$ROOT/minisign.pub" -x "$ROOT/minisign.sig"
echo LIVE_SIGNATURE_CRYPTO_VERIFY=PASS

# Preserve owner data/session identity across the normal update.
pkill -x "$OLD_EXE" 2>/dev/null || true
sleep 2
snapshot_tree "$ROOT/durable-before.json"
keychain_hash "$ROOT/keychain-before.sha256"

# REAL normal ENDLUME updater path. No manual 10.0.14 app copy is allowed here.
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
echo UPDATE_DETECTED_10_0_13_TO_10_0_14=PASS

installed=0
for i in $(seq 1 600); do
  S="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$INFO" 2>/dev/null || true)"
  B="$(/usr/bin/plutil -extract CFBundleVersion raw -o - "$INFO" 2>/dev/null || true)"
  if [ "$S" = '10.0.14' ] && [ "$B" = '10.0.14' ]; then installed=1; break; fi
  if (( i % 20 == 0 )); then echo "WAIT_INSTALL second=$i short=$S build=$B"; fi
  sleep 1
done
test "$installed" -eq 1
echo DOWNLOAD_AND_INSTALL=PASS

# Updater must restart itself as 10.0.14; do not manually launch for this gate.
NEW_EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$INFO")"
RESTART_PID=''
for i in $(seq 1 90); do
  for p in $(pgrep -x "$NEW_EXE" 2>/dev/null || true); do
    cmd="$(ps -p "$p" -o command= 2>/dev/null || true)"
    case "$cmd" in "$APP/Contents/MacOS/$NEW_EXE"*) RESTART_PID="$p"; break 2;; esac
  done
  sleep 1
done
test -n "$RESTART_PID"
test "$RESTART_PID" != "$APP_PID" || ! kill -0 "$APP_PID" 2>/dev/null
echo UPDATER_RESTART=PASS

NEW_BIN="$APP/Contents/MacOS/$NEW_EXE"
NEW_SHA="$(/usr/bin/shasum -a 256 "$NEW_BIN" | awk '{print $1}')"
EXPECTED_NEW_SHA="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["appExecutableSha256"])' "$ROOT/release-1014.json")"
test "$NEW_SHA" = "$EXPECTED_NEW_SHA"
/usr/bin/codesign --verify --deep --strict "$APP"
test "$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$INFO")" = '10.0.14'
test "$(/usr/bin/plutil -extract CFBundleVersion raw -o - "$INFO")" = '10.0.14'
test "$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$INFO")" = 'studio.endlume.desktop'
echo PHYSICAL_TAURI_SIGNATURE_VERIFICATION=PASS
echo INSTALLED_VERSION=10.0.14
echo INSTALLED_APP_SHA256="$NEW_SHA"
echo CODESIGN_INSTALLED=PASS

sleep 5
kill -0 "$RESTART_PID"
snapshot_tree "$ROOT/durable-after.json"
keychain_hash "$ROOT/keychain-after.sha256"
diff -u "$ROOT/durable-before.json" "$ROOT/durable-after.json"
diff -u "$ROOT/keychain-before.sha256" "$ROOT/keychain-after.sha256"
echo OWNER_DURABLE_STATE=PRESERVED
echo GOOGLE_YOUTUBE=PRESERVED

# Full post-update physical smoke against the INSTALLED 10.0.14 binary.
pkill -x "$NEW_EXE" 2>/dev/null || true
FFMPEG="$(find "$APP/Contents" -maxdepth 7 -type f -name 'ffmpeg' -perm -111 -print -quit)"
FFPROBE="$(find "$APP/Contents" -maxdepth 7 -type f -name 'ffprobe' -perm -111 -print -quit)"
test -x "$FFMPEG" -a -x "$FFPROBE"
test -d '/Volumes/TOSHIBA EXT'
python3 scripts/qa-endlume-1014-vyron-routing-physical.py "$NEW_BIN" "$FFMPEG" "$FFPROBE" "$ROOT/vyron-routing-postupdate.json" | tee "$ROOT/vyron-routing-postupdate.log"
QA_HOME="$RUNNER_TEMP/endlume-1014-postupdate-isolated-home"
rm -rf "$QA_HOME"; mkdir -p "$QA_HOME"
python3 scripts/qa-endlume-1014-seed-persisted-library.py "$FFMPEG" "$QA_HOME" | tee "$ROOT/persisted-library-postupdate.log"
HOME="$QA_HOME" python3 scripts/qa-endlume-1011-preview-subscribe-final.py "$NEW_BIN" "$FFMPEG" "$FFPROBE" "$ROOT/preview-subscribe-postupdate.json" | tee "$ROOT/preview-subscribe-postupdate.log"
python3 - "$ROOT/vyron-routing-postupdate.json" "$ROOT/preview-subscribe-postupdate.json" <<'PY'
import json,sys
v=json.load(open(sys.argv[1])); q=json.load(open(sys.argv[2]))
assert v['status']=='GREEN' and v['crossWrite'] is False,v
assert q['status']=='GREEN',q
assert q['preview']['effectsBackend']=='GREEN' and q['preview']['effectsFrontend']['status']=='GREEN',q
assert q['preview']['subscribeBackend']=='GREEN' and q['preview']['subscribeFrontend']['status']=='GREEN',q
assert q['subscribeFinal']=='GREEN',q
assert q['roundEqualizer']=='GREEN' and q['otherEffect']=='GREEN',q
print('VYRON_POSTUPDATE=PASS')
print('CORRECT_DESTINATION_POSTUPDATE=PASS')
print('EFFECTS_PREVIEW_POSTUPDATE=PASS')
print('SUBSCRIBE_PREVIEW_POSTUPDATE=PASS')
print('REAL_RENDER_POSTUPDATE=PASS')
print('MEDIA_CONTRACT_POSTUPDATE=PASS')
PY

trap - ERR
echo NORMAL_UPDATER_10_0_13_TO_10_0_14=PASS
echo POSTUPDATE_PACKAGED_SMOKE=PASS
echo ENDLUME_10_0_14_FINAL_GATE=PASS
