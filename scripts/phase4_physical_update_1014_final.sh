#!/bin/bash
set -Eeuo pipefail

BASE='scripts/phase4_physical_update_1014.sh'
python3 - "$BASE" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
old=r'''restore_production_1013(){
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
'''
new=r'''release_upload_retry_1013(){
  local attempt rc=1
  for attempt in 1 2 3 4 5 6 7 8; do
    if gh release upload "$STABLE_TAG" "$@" --clobber --repo "$STABLE_REPO"; then
      echo "ROLLBACK_UPLOAD_PASS attempt=$attempt files=$*" >&2
      return 0
    else
      rc=$?
      echo "ROLLBACK_UPLOAD_RETRY attempt=$attempt rc=$rc files=$*" >&2
      sleep $((attempt*2))
    fi
  done
  return "$rc"
}
restore_production_1013(){
  trap - ERR
  set +e
  echo ROLLBACK_10_0_13=START >&2
  release_upload_retry_1013 "$ROLLBACK_DIR/ENDLUME-macos-aarch64.app.tar.gz" "$ROLLBACK_DIR/ENDLUME-macos-aarch64.app.tar.gz.sig"
  r1=$?
  release_upload_retry_1013 "$ROLLBACK_DIR/latest.json"
  r2=$?
  if [ "$r1" -ne 0 ] || [ "$r2" -ne 0 ]; then
    echo "ROLLBACK_UPLOAD_FAILED tar_sig_rc=$r1 latest_rc=$r2" >&2
  fi
  sleep 3
  cache="rollback-verify-$(date +%s)-${GITHUB_RUN_ID:-local}"
  curl -fL --retry 8 --retry-all-errors "$BASE_URL/latest.json?$cache" -o "$ROOT/rollback-live.json"
  curl -fL --retry 8 --retry-all-errors "$BASE_URL/ENDLUME-macos-aarch64.app.tar.gz?$cache" -o "$ROOT/rollback-live.tar.gz"
  curl -fL --retry 8 --retry-all-errors "$BASE_URL/ENDLUME-macos-aarch64.app.tar.gz.sig?$cache" -o "$ROOT/rollback-live.tar.gz.sig"
  python3 - "$ROOT/rollback-live.json" "$ROOT/rollback-live.tar.gz" "$ROOT/rollback-live.tar.gz.sig" <<'PY'
import hashlib,json,sys
latest,tar,sig=sys.argv[1:]
m=json.load(open(latest)); assert m['version']=='10.0.13',m
p=m['platforms']['darwin-aarch64']
sha=hashlib.sha256(open(tar,'rb').read()).hexdigest(); sigtxt=open(sig).read().strip()
assert p['sha256']==sha,(p.get('sha256'),sha)
assert p['signature']==sigtxt
print('ROLLBACK_LIVE_VERSION=10.0.13')
print('ROLLBACK_LIVE_SHA256='+sha)
print('ROLLBACK_LIVE_CHANNEL=PASS')
PY
  verify_rc=$?
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
  if [ "$r1" -eq 0 ] && [ "$r2" -eq 0 ] && [ "$verify_rc" -eq 0 ]; then
    echo ROLLBACK_10_0_13=COMPLETE >&2
    return 0
  fi
  echo "ROLLBACK_10_0_13=FAILED tar_sig_rc=$r1 latest_rc=$r2 verify_rc=$verify_rc" >&2
  return 1
}
'''
if old not in s:
    raise SystemExit('restore_production_1013 block not found')
p.write_text(s.replace(old,new,1))
PY

# The base updater harness is now retry-hardened in this checkout only.
exec /bin/bash scripts/phase4_physical_update_1014_vision_retry.sh
