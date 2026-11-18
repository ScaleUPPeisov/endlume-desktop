#!/bin/bash
set -Eeuo pipefail
umask 077
APP=/Applications/VYRON.app
BASE="$HOME/.vyron-owner-rollback"
DATA="$HOME/Library/Application Support/studio.channelflow.desktop"
WEBKIT="$HOME/Library/WebKit/studio.channelflow.desktop"
APPID=studio.channelflow.desktop
SOURCE=08bef81a3683b788de5ff734612a9e9f6d94f920
PIN=1c97657fd2a7ba4c2a0ce5b5361518eeacf76da274521b1977d57a55b8dbcec9
if [ "$(uname -m)" != arm64 ]; then echo "INSTALL_WRONG_ARCH"; exit 1; fi
if [ ! -d "$BASE" ] || [ ! -d "$DATA" ] || [ ! -d "$WEBKIT" ]; then echo "INSTALL_REQUIRED_DATA_MISSING"; exit 1; fi
STAGES=()
while IFS= read -r p; do STAGES+=("$p"); done < <(find "$BASE" -mindepth 1 -maxdepth 1 -type d -name 'staged-621-local-bootstrap-*' -print)
if [ "${#STAGES[@]}" -ne 1 ]; then echo "INSTALL_STAGE_COUNT_NOT_ONE"; exit 1; fi
STAGE="${STAGES[0]}"
SRC="$STAGE/VYRON.app"
MARK="$STAGE/VERIFIED"
test -d "$SRC" && test ! -L "$SRC" && test -f "$MARK" && test ! -L "$MARK"
grep -Fxq "source=$SOURCE" "$MARK"
grep -Fxq 'version=6.1.21' "$MARK"
grep -Fxq "approved_pubkey_sha256=$PIN" "$MARK"
grep -Fxq 'bootstrap_ad_hoc=YES' "$MARK"
grep -Fxq 'updater_archive=NOT_SIGNED_NOT_DISTRIBUTABLE' "$MARK"
test -d "$APP" && test ! -L "$APP"
test -w /Applications && test -w "$APP"
plist(){ /usr/libexec/PlistBuddy -c "Print :$2" "$1/Contents/Info.plist"; }
test "$(plist "$APP" CFBundleShortVersionString)" = 6.1.20
test "$(plist "$SRC" CFBundleShortVersionString)" = 6.1.21
for p in "$APP" "$SRC"; do
  test "$(plist "$p" CFBundleIdentifier)" = "$APPID"
  /usr/bin/codesign --verify --deep --strict "$p" >/dev/null 2>&1
done
EXENAME="$(plist "$SRC" CFBundleExecutable)"
test "$EXENAME" = "$(plist "$APP" CFBundleExecutable)"
/usr/bin/lipo -archs "$SRC/Contents/MacOS/$EXENAME" | tr ' ' '\n' | grep -Fxq arm64
NEW_SHA="$(sed -n 's/^executable_sha256=//p' "$MARK")"
test "$NEW_SHA" = "$(shasum -a 256 "$SRC/Contents/MacOS/$EXENAME" | awk '{print $1}')"
OLD_SHA="$(shasum -a 256 "$APP/Contents/MacOS/$EXENAME" | awk '{print $1}')"
test "$NEW_SHA" != "$OLD_SHA"
if /usr/bin/xattr -p com.apple.quarantine "$SRC" >/dev/null 2>&1; then echo "INSTALL_STAGED_APP_QUARANTINED"; exit 1; fi

queue_guard() {
  /usr/bin/python3 - <<'PY'
import json,sqlite3
from pathlib import Path
from urllib.parse import quote
h=Path.home()
s=json.loads((h/'Library'/'Application Support'/'studio.channelflow.desktop'/'state.json').read_text())
channels=s.get('channels');jobs=s.get('jobs')
if not isinstance(channels,list) or len(channels)!=33 or not isinstance(jobs,list):
  raise SystemExit('VYRON_INSTALL_OWNER_CHANNELS_OR_JOBS_INVALID')
active=sum(1 for j in jobs if isinstance(j,dict) and str(j.get('status')) in ('UPLOADING','RENDERING','PROCESSING','DOWNLOADING','RUNNING'))
found=0;queued=0
for p in (h/'Library'/'WebKit'/'studio.channelflow.desktop').rglob('*'):
  if not p.is_file() or p.suffix.lower() not in ('.sqlite3','.db') or p.stat().st_size>50_000_000:continue
  try:
    db=sqlite3.connect('file:'+quote(str(p))+'?mode=ro',uri=True,timeout=2)
    try:
      if not db.execute("SELECT name FROM sqlite_master WHERE name='ItemTable'").fetchone():continue
      for k,v in db.execute("SELECT key,value FROM ItemTable WHERE key IN (?,?)",('vyron:youtube-upload-queue:v1','vyron:youtube-upload-queue:v1:staging')):
        payloads=[v.decode('utf-16le','ignore'),v.decode('utf-8','ignore')] if isinstance(v,bytes) else [str(v)]
        for value in payloads:
          try:d=json.loads(value)
          except (ValueError,TypeError):continue
          if isinstance(d,dict) and isinstance(d.get('entries'),list):
            found+=1
            queued+=sum(1 for e in d['entries'] if isinstance(e,dict) and e.get('state') in ('RUNNING','QUEUED'))
            break
    finally:db.close()
  except (OSError,ValueError,sqlite3.Error):pass
print('VYRON_INSTALL_CHANNELS='+str(len(channels)))
print('VYRON_INSTALL_ACTIVE_JOBS='+str(active))
print('VYRON_INSTALL_ACTIVE_QUEUE='+str(queued))
print('VYRON_INSTALL_QUEUE_SNAPSHOTS='+str(found))
if active or queued or found<1:raise SystemExit('INSTALL_ABORT_ACTIVE_OR_UNKNOWN_UPLOAD_QUEUE')
print('VYRON_INSTALL_IDLE_GUARD=PASS')
PY
}
queue_guard
if /usr/bin/pgrep -x channelflow >/dev/null 2>&1; then
  /usr/bin/osascript -e 'with timeout of 15 seconds' -e 'tell application id "studio.channelflow.desktop" to quit' -e 'end timeout' >/dev/null 2>&1 || { echo "INSTALL_QUIT_REFUSED"; exit 1; }
  for _ in $(seq 1 30); do
    if ! /usr/bin/pgrep -x channelflow >/dev/null 2>&1; then break; fi
    sleep 1
  done
fi
if /usr/bin/pgrep -x channelflow >/dev/null 2>&1; then echo "INSTALL_APP_STILL_RUNNING"; exit 1; fi
queue_guard
APP_KB="$(du -sk "$APP" | awk '{print $1}')"
NEW_KB="$(du -sk "$SRC" | awk '{print $1}')"
DATA_KB="$(du -sk "$DATA" | awk '{print $1}')"
WEBKIT_KB="$(du -sk "$WEBKIT" | awk '{print $1}')"
test "$DATA_KB" -lt 1048576 && test "$WEBKIT_KB" -lt 1048576
NEED=$((2*APP_KB + NEW_KB + DATA_KB + WEBKIT_KB + 1048576))
FREE="$(df -Pk /Applications | awk 'END {print $4}')"
test "$FREE" -gt "$NEED"
BACKUP="$(mktemp -d "$BASE/owner-pre621-bootstrap-live-XXXXXX")"
/usr/bin/ditto "$APP" "$BACKUP/VYRON.app"
/usr/bin/ditto "$DATA" "$BACKUP/application-support"
/usr/bin/ditto "$WEBKIT" "$BACKUP/webkit"
/usr/bin/codesign --verify --deep --strict "$BACKUP/VYRON.app" >/dev/null 2>&1
test "$(shasum -a 256 "$BACKUP/VYRON.app/Contents/MacOS/$EXENAME" | awk '{print $1}')" = "$OLD_SHA"
/usr/bin/python3 - "$BACKUP/application-support/state.json" <<'PY'
import json,sys
with open(sys.argv[1]) as f:s=json.load(f)
assert len(s['channels'])==33
print('VYRON_INSTALL_BACKUP_33_CHANNELS=PASS')
PY
echo "VYRON_621_BACKUP=PASS"
echo "VYRON_621_BACKUP_FOLDER=$(basename "$BACKUP")"
TEMP="$(mktemp -d /Applications/.vyron-621-bootstrap-install-XXXXXX)"
/usr/bin/ditto "$SRC" "$TEMP/VYRON.app"
/usr/bin/codesign --verify --deep --strict "$TEMP/VYRON.app" >/dev/null 2>&1
test "$(shasum -a 256 "$TEMP/VYRON.app/Contents/MacOS/$EXENAME" | awk '{print $1}')" = "$NEW_SHA"
SWAPPED=0
rollback(){
  local result="$1"
  trap - ERR
  if [ "$SWAPPED" = 1 ]; then
    echo 'VYRON_621_ROLLBACK_START=YES'
    if /usr/bin/pgrep -x channelflow >/dev/null 2>&1; then
      /usr/bin/osascript -e 'with timeout of 8 seconds' -e 'tell application id "studio.channelflow.desktop" to quit' -e 'end timeout' >/dev/null 2>&1 || true
      sleep 3
    fi
    if /usr/bin/pgrep -x channelflow >/dev/null 2>&1; then
      echo 'VYRON_621_ROLLBACK_BUSY=REQUIRES_MANUAL_RECOVERY'
    else
      if [ -d "$APP" ]; then mv "$APP" "$TEMP/failed-621.app" || true; fi
      if [ -d "$TEMP/VYRON-6.1.20.app" ]; then mv "$TEMP/VYRON-6.1.20.app" "$APP" || true; fi
      if [ -d "$APP" ]; then
        /usr/bin/codesign --verify --deep --strict "$APP" >/dev/null 2>&1 || true
        /usr/bin/env -u RUNNER_TRACKING_ID /usr/bin/open -a "$APP" || true
      fi
      echo 'VYRON_621_ROLLBACK_620_BUNDLE_ATTEMPTED=YES'
    fi
    echo "VYRON_621_ROLLBACK_OWNER_DATA_BACKUP_PRESERVED=$(basename "$BACKUP")"
  fi
  exit "$result"
}
trap 'rollback "$?"' ERR
mv "$APP" "$TEMP/VYRON-6.1.20.app"
SWAPPED=1
mv "$TEMP/VYRON.app" "$APP"
/usr/bin/codesign --verify --deep --strict "$APP" >/dev/null 2>&1
test "$(plist "$APP" CFBundleShortVersionString)" = 6.1.21
test "$(shasum -a 256 "$APP/Contents/MacOS/$EXENAME" | awk '{print $1}')" = "$NEW_SHA"
echo 'VYRON_621_INSTALLED_BUNDLE=PASS'
/usr/bin/env -u RUNNER_TRACKING_ID /usr/bin/open -a "$APP"
sleep 12
if ! /usr/bin/pgrep -x channelflow >/dev/null 2>&1; then echo "VYRON_621_RELAUNCH_FAILED"; false; fi
/usr/bin/python3 - <<'PY'
import json
from pathlib import Path
d=json.loads((Path.home()/'Library'/'Application Support'/'studio.channelflow.desktop'/'state.json').read_text())
assert len(d['channels'])==33
print('VYRON_621_POSTINSTALL_CHANNELS=33')
PY
SWAPPED=0
trap - ERR
echo 'VYRON_621_LOCAL_BOOTSTRAP_INSTALLED=PASS'
echo 'VYRON_621_APP_RUNNING=YES'
echo 'VYRON_621_ROLLBACK_BUNDLE_RETAINED=YES'
echo 'VYRON_621_OWNER_DATA_BACKUP_RETAINED=YES'
echo 'VYRON_STABLE_FEED=UNCHANGED'
