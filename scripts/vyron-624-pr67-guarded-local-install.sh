#!/bin/bash
set -Eeuo pipefail
umask 077
APP=/Applications/VYRON.app
BASE="$HOME/.vyron-owner-rollback"
DATA="$HOME/Library/Application Support/studio.channelflow.desktop"
WEBKIT="$HOME/Library/WebKit/studio.channelflow.desktop"
APPID=studio.channelflow.desktop
SOURCE=6b3a21438bcdfecab69a73366dc56dc6b4f5b6c0
PIN=1c97657fd2a7ba4c2a0ce5b5361518eeacf76da274521b1977d57a55b8dbcec9
if [ "$(uname -m)" != arm64 ]; then echo "INSTALL_WRONG_ARCH"; exit 1; fi
if [ ! -d "$BASE" ] || [ ! -d "$DATA" ] || [ ! -d "$WEBKIT" ]; then echo "INSTALL_REQUIRED_DATA_MISSING"; exit 1; fi
STAGES=()
while IFS= read -r p; do STAGES+=("$p"); done < <(find "$BASE" -mindepth 1 -maxdepth 1 -type d -name 'staged-624-pr67-hosted-*' -print)
if [ "${#STAGES[@]}" -ne 1 ]; then echo "INSTALL_STAGE_COUNT_NOT_ONE"; exit 1; fi
STAGE="${STAGES[0]}"
SRC="$STAGE/VYRON.app"
MARK="$STAGE/VERIFIED"
test -d "$SRC" && test ! -L "$SRC" && test -f "$MARK" && test ! -L "$MARK"
grep -Fxq "source=$SOURCE" "$MARK"
grep -Fxq 'version=6.1.24' "$MARK"
grep -Fxq "approved_pubkey_sha256=$PIN" "$MARK"
grep -Fxq 'bootstrap_ad_hoc=YES' "$MARK"
grep -Fxq 'updater_archive=NOT_SIGNED_NOT_DISTRIBUTABLE' "$MARK"
test -d "$APP" && test ! -L "$APP"
test -w /Applications && test -w "$APP"
plist(){ /usr/libexec/PlistBuddy -c "Print :$2" "$1/Contents/Info.plist"; }
test "$(plist "$APP" CFBundleShortVersionString)" = 6.1.23
test "$(plist "$SRC" CFBundleShortVersionString)" = 6.1.24
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
BACKUPS=()
while IFS= read -r p; do BACKUPS+=("$p"); done < <(find "$BASE" -mindepth 1 -maxdepth 1 -type d -name 'pr67-pre624-from623-*' -print)
if [ "${#BACKUPS[@]}" -ne 1 ]; then echo 'VYRON_624_BACKUP_NOT_UNIQUE'; exit 1; fi
BACKUP="${BACKUPS[0]}"
test ! -L "$BACKUP"
test -d "$BACKUP/VYRON.app" && test -d "$BACKUP/application-support"
test -d "$BACKUP/sqlite-online" && test -d "$BACKUP/webkit-auxiliary"
test -f "$BACKUP/BACKUP-STATUS.txt"
grep -Fxq 'channels=33' "$BACKUP/BACKUP-STATUS.txt"
grep -Fxq 'source=VYRON 6.1.23' "$BACKUP/BACKUP-STATUS.txt"
grep -Fxq 'sqlite_online=VERIFIED' "$BACKUP/BACKUP-STATUS.txt"
/usr/bin/codesign --verify --deep --strict "$BACKUP/VYRON.app"
test "$(shasum -a 256 "$BACKUP/VYRON.app/Contents/MacOS/$EXENAME" | awk '{print $1}')" = "$OLD_SHA"
/usr/bin/python3 - "$BACKUP" <<'PY'
import json,sqlite3,sys
from pathlib import Path
from urllib.parse import quote
b=Path(sys.argv[1])
assert len(json.loads((b/'application-support'/'state.json').read_text())['channels'])==33
files=[p for p in (b/'sqlite-online').rglob('*') if p.is_file() and p.suffix.lower() in ('.db','.sqlite','.sqlite3')]
assert len(files)>=5,'SQLITE_BACKUP_COUNT_LOW'
for p in files:
  db=sqlite3.connect('file:'+quote(str(p))+'?mode=ro',uri=True)
  try: assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
  finally: db.close()
print('EXISTING_BACKUP_SQLITE_VERIFIED='+str(len(files)))
PY
echo "VYRON_624_BACKUP=EXISTING_VERIFIED"
echo "VYRON_624_BACKUP_FOLDER=$(basename "$BACKUP")"
TEMP="$(mktemp -d /Applications/.vyron-624-bootstrap-install-XXXXXX)"
/usr/bin/ditto "$SRC" "$TEMP/VYRON.app"
/usr/bin/codesign --verify --deep --strict "$TEMP/VYRON.app" >/dev/null 2>&1
test "$(shasum -a 256 "$TEMP/VYRON.app/Contents/MacOS/$EXENAME" | awk '{print $1}')" = "$NEW_SHA"
SWAPPED=0
rollback(){
  local result="$1"
  trap - ERR
  if [ "$SWAPPED" = 1 ]; then
    echo 'VYRON_624_ROLLBACK_START=YES'
    if /usr/bin/pgrep -x channelflow >/dev/null 2>&1; then
      /usr/bin/osascript -e 'with timeout of 8 seconds' -e 'tell application id "studio.channelflow.desktop" to quit' -e 'end timeout' >/dev/null 2>&1 || true
      sleep 3
    fi
    if /usr/bin/pgrep -x channelflow >/dev/null 2>&1; then
      echo 'VYRON_624_ROLLBACK_BUSY=REQUIRES_MANUAL_RECOVERY'
    else
      if [ -d "$APP" ]; then mv "$APP" "$TEMP/failed-624.app" || true; fi
      if [ -d "$TEMP/VYRON-6.1.23.app" ]; then mv "$TEMP/VYRON-6.1.23.app" "$APP" || true; fi
      if [ -d "$APP" ]; then
        /usr/bin/codesign --verify --deep --strict "$APP" >/dev/null 2>&1 || true
        /usr/bin/env -u RUNNER_TRACKING_ID /usr/bin/open -a "$APP" || true
      fi
      echo 'VYRON_624_ROLLBACK_622_BUNDLE_ATTEMPTED=YES'
    fi
    echo "VYRON_624_ROLLBACK_OWNER_DATA_BACKUP_PRESERVED=$(basename "$BACKUP")"
  fi
  exit "$result"
}
trap 'rollback "$?"' ERR
mv "$APP" "$TEMP/VYRON-6.1.23.app"
SWAPPED=1
mv "$TEMP/VYRON.app" "$APP"
/usr/bin/codesign --verify --deep --strict "$APP" >/dev/null 2>&1
test "$(plist "$APP" CFBundleShortVersionString)" = 6.1.24
test "$(shasum -a 256 "$APP/Contents/MacOS/$EXENAME" | awk '{print $1}')" = "$NEW_SHA"
echo 'VYRON_624_INSTALLED_BUNDLE=PASS'
/usr/bin/env -u RUNNER_TRACKING_ID /usr/bin/open -a "$APP"
sleep 12
if ! /usr/bin/pgrep -x channelflow >/dev/null 2>&1; then echo "VYRON_624_RELAUNCH_FAILED"; false; fi
/usr/bin/python3 - <<'PY'
import json
from pathlib import Path
d=json.loads((Path.home()/'Library'/'Application Support'/'studio.channelflow.desktop'/'state.json').read_text())
assert len(d['channels'])==33
print('VYRON_624_POSTINSTALL_CHANNELS=33')
PY
# Actual relaunch smoke test on physical M1. Keep original bundle for rollback.
queue_guard
/usr/bin/osascript -e 'with timeout of 15 seconds' -e 'tell application id "studio.channelflow.desktop" to quit' -e 'end timeout' >/dev/null 2>&1
for _ in $(seq 1 25); do
  if ! /usr/bin/pgrep -x channelflow >/dev/null 2>&1; then break; fi
  sleep 1
done
if /usr/bin/pgrep -x channelflow >/dev/null 2>&1; then echo 'VYRON_624_RESTART_QUIT_FAILED'; false; fi
/usr/bin/env -u RUNNER_TRACKING_ID /usr/bin/open -a "$APP"
sleep 12
/usr/bin/pgrep -x channelflow >/dev/null
test "$(plist "$APP" CFBundleShortVersionString)" = 6.1.24
queue_guard
echo 'VYRON_624_RESTART=PASS'
# Read-only display evidence check of persisted WebKit runway; do not modify or refresh YouTube.
 /usr/bin/python3 - <<'PY'
import json,sqlite3
from pathlib import Path
from urllib.parse import quote
root=Path.home()/'Library'/'WebKit'/'studio.channelflow.desktop'
found=None
for p in root.rglob('*'):
  if p.is_symlink() or not p.is_file() or p.suffix.lower() not in ('.sqlite','.sqlite3','.db') or p.stat().st_size>50000000:continue
  try:
    db=sqlite3.connect('file:'+quote(str(p))+'?mode=ro',uri=True,timeout=2)
    try:
      if not db.execute("SELECT name FROM sqlite_master WHERE name='ItemTable'").fetchone():continue
      for (v,) in db.execute("SELECT value FROM ItemTable WHERE key='vyron:channel-runway:v1'"):
        candidates=[v.decode('utf-16le','ignore'),v.decode('utf-8','ignore')] if isinstance(v,bytes) else [str(v)]
        for s in candidates:
          try: o=json.loads(s)
          except (TypeError,ValueError):continue
          if isinstance(o,dict) and isinstance(o.get('channels'),dict):
            if found is None or len(o['channels'])>len(found['channels']):found=o
    finally:db.close()
  except (sqlite3.Error,OSError):pass
if found is None:
  print('HISTORICAL_RUNWAY_WEBKIT=NOT_FOUND')
else:
  rows=found['channels'];print('HISTORICAL_RUNWAY_RECORDS='+str(len(rows)))
  for name in ('Neon Drive FM','Afterglow Highway','Lumière de Minuit'):
    for r in rows.values():
      if isinstance(r,dict) and r.get('channelName')==name:
        print('HISTORICAL_CHANNEL='+name+'|state='+str(r.get('dataState','UNKNOWN'))+'|scheduled='+str(r.get('scheduledVideoCount','UNKNOWN'))+'|until='+str(r.get('scheduledUntil','UNKNOWN')))
        break
    else:print('HISTORICAL_CHANNEL='+name+'|record=MISSING')
PY
SWAPPED=0
trap - ERR
echo "VYRON_624_INSTALLED_SOURCE_SHA=$SOURCE"
echo "VYRON_624_INSTALLED_EXECUTABLE_SHA256=$NEW_SHA"
echo 'VYRON_624_LOCAL_BOOTSTRAP_INSTALLED=PASS'
echo 'VYRON_624_APP_RUNNING=YES'
echo 'VYRON_624_ROLLBACK_BUNDLE_RETAINED=YES'
echo 'VYRON_624_OWNER_DATA_BACKUP_RETAINED=YES'
echo 'VYRON_STABLE_FEED=UNCHANGED'
