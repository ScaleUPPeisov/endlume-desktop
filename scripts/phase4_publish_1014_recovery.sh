#!/bin/bash
set -Eeuo pipefail

: "${GH_TOKEN:?GH_TOKEN missing}"
: "${RUNNER_TEMP:?RUNNER_TEMP missing}"

STABLE_REPO='ScaleUPPeisov/scaleup-site'
STABLE_TAG='endlume-stable'
BASE_URL="https://github.com/$STABLE_REPO/releases/download/$STABLE_TAG"
KNOWN_GOOD_ROLLBACK_RUN='38257054613'
KNOWN_GOOD_ROLLBACK_ARTIFACT='ENDLUME-10.0.13-STABLE-ROLLBACK'

release_upload_retry(){
  local attempt rc=1
  for attempt in 1 2 3 4 5 6 7 8; do
    if gh release upload "$STABLE_TAG" "$@" --clobber --repo "$STABLE_REPO"; then
      echo "GH_RELEASE_UPLOAD_PASS attempt=$attempt files=$*"
      return 0
    else
      rc=$?
      echo "GH_RELEASE_UPLOAD_RETRY attempt=$attempt rc=$rc files=$*" >&2
      sleep $((attempt*2))
    fi
  done
  return "$rc"
}

verify_1013_channel(){
  local dir="$1"
  python3 - "$dir/latest.json" "$dir/ENDLUME-macos-aarch64.app.tar.gz" "$dir/ENDLUME-macos-aarch64.app.tar.gz.sig" <<'PY'
import hashlib,json,sys
latest,tar,sig=sys.argv[1:]
m=json.load(open(latest)); assert m['version']=='10.0.13',m
p=m['platforms']['darwin-aarch64']
sha=hashlib.sha256(open(tar,'rb').read()).hexdigest()
sigtxt=open(sig).read().strip()
assert p['sha256']==sha,(p.get('sha256'),sha)
assert p['signature']==sigtxt
assert p['url']=='https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/ENDLUME-macos-aarch64.app.tar.gz'
print('VERIFIED_10_0_13_SHA256='+sha)
PY
}

repair_1013_if_needed(){
  local probe="$RUNNER_TEMP/endlume-1013-live-probe"
  local cache="repair-$(date +%s)-${GITHUB_RUN_ID:-local}"
  rm -rf "$probe"; mkdir -p "$probe"
  curl -fL --retry 5 --retry-all-errors "$BASE_URL/latest.json?$cache" -o "$probe/latest.json"
  local version
  version="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$probe/latest.json")"
  echo "PRE_REPAIR_LIVE_VERSION=$version"
  if [ "$version" != '10.0.13' ]; then
    echo "PRE_REPAIR_NOT_10_0_13_SKIP=$version"
    return 0
  fi

  set +e
  curl -fL --retry 3 --retry-all-errors "$BASE_URL/ENDLUME-macos-aarch64.app.tar.gz?$cache" -o "$probe/ENDLUME-macos-aarch64.app.tar.gz"
  local tar_rc=$?
  curl -fL --retry 3 --retry-all-errors "$BASE_URL/ENDLUME-macos-aarch64.app.tar.gz.sig?$cache" -o "$probe/ENDLUME-macos-aarch64.app.tar.gz.sig"
  local sig_rc=$?
  set -e
  if [ "$tar_rc" -eq 0 ] && [ "$sig_rc" -eq 0 ] && verify_1013_channel "$probe" >/dev/null 2>&1; then
    echo LIVE_10_0_13_CANONICAL=HEALTHY
    return 0
  fi

  echo LIVE_10_0_13_CANONICAL=REPAIR_REQUIRED
  local rb="$RUNNER_TEMP/endlume-1013-emergency-restore"
  rm -rf "$rb"; mkdir -p "$rb"
  gh run download "$KNOWN_GOOD_ROLLBACK_RUN" --repo ScaleUPPeisov/endlume-desktop --name "$KNOWN_GOOD_ROLLBACK_ARTIFACT" --dir "$rb"
  test -s "$rb/latest.json"
  test -s "$rb/ENDLUME-macos-aarch64.app.tar.gz"
  test -s "$rb/ENDLUME-macos-aarch64.app.tar.gz.sig"
  verify_1013_channel "$rb"

  release_upload_retry "$rb/ENDLUME-macos-aarch64.app.tar.gz" "$rb/ENDLUME-macos-aarch64.app.tar.gz.sig"
  release_upload_retry "$rb/latest.json"
  sleep 3

  rm -rf "$probe"; mkdir -p "$probe"
  curl -fL --retry 5 --retry-all-errors "$BASE_URL/latest.json?$cache-after" -o "$probe/latest.json"
  curl -fL --retry 5 --retry-all-errors "$BASE_URL/ENDLUME-macos-aarch64.app.tar.gz?$cache-after" -o "$probe/ENDLUME-macos-aarch64.app.tar.gz"
  curl -fL --retry 5 --retry-all-errors "$BASE_URL/ENDLUME-macos-aarch64.app.tar.gz.sig?$cache-after" -o "$probe/ENDLUME-macos-aarch64.app.tar.gz.sig"
  verify_1013_channel "$probe"
  echo LIVE_10_0_13_CANONICAL=REPAIRED
}

repair_1013_if_needed

# Harden the existing audited publisher at runtime without altering product code.
CORE='scripts/phase4_publish_1014.sh'
TMP="$RUNNER_TEMP/phase4_publish_1014_recovery_runtime.sh"
python3 - "$CORE" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text()
marker='MUTATED=0\n'
helper=r'''release_upload_retry(){
  local attempt rc=1
  for attempt in 1 2 3 4 5 6 7 8; do
    if gh release upload "$STABLE_TAG" "$@" --clobber --repo "$STABLE_REPO"; then
      echo "GH_RELEASE_UPLOAD_PASS attempt=$attempt files=$*"
      return 0
    else
      rc=$?
      echo "GH_RELEASE_UPLOAD_RETRY attempt=$attempt rc=$rc files=$*" >&2
      sleep $((attempt*2))
    fi
  done
  return "$rc"
}
'''
assert marker in src
src=src.replace(marker,helper+'\n'+marker,1)
old=r'''rollback_on_error(){
  rc=$?
  if [ "$MUTATED" = 1 ]; then
    echo "PUBLISH_FAILURE_ROLLBACK=START rc=$rc" >&2
    gh release upload "$STABLE_TAG" "$ROLLBACK_DIR/ENDLUME-macos-aarch64.app.tar.gz" "$ROLLBACK_DIR/ENDLUME-macos-aarch64.app.tar.gz.sig" --clobber --repo "$STABLE_REPO" || true
    gh release upload "$STABLE_TAG" "$ROLLBACK_DIR/latest.json" --clobber --repo "$STABLE_REPO" || true
    echo PUBLISH_FAILURE_ROLLBACK=RESTORED_10_0_13 >&2
  fi
  exit "$rc"
}
'''
new=r'''rollback_on_error(){
  rc=$?
  trap - ERR
  if [ "$MUTATED" = 1 ]; then
    echo "PUBLISH_FAILURE_ROLLBACK=START rc=$rc" >&2
    set +e
    release_upload_retry "$ROLLBACK_DIR/ENDLUME-macos-aarch64.app.tar.gz" "$ROLLBACK_DIR/ENDLUME-macos-aarch64.app.tar.gz.sig"
    r1=$?
    release_upload_retry "$ROLLBACK_DIR/latest.json"
    r2=$?
    set -e
    if [ "$r1" -eq 0 ] && [ "$r2" -eq 0 ]; then
      echo PUBLISH_FAILURE_ROLLBACK=RESTORED_10_0_13 >&2
    else
      echo "PUBLISH_FAILURE_ROLLBACK=FAILED tar_sig_rc=$r1 latest_rc=$r2" >&2
    fi
  fi
  exit "$rc"
}
'''
assert old in src
src=src.replace(old,new,1)
repls={
'gh release upload "$STABLE_TAG" "$ZIP" "$VTAR" "$VSIG" "$RELEASE_JSON" "$SUMS" --clobber --repo "$STABLE_REPO"':'release_upload_retry "$ZIP" "$VTAR" "$VSIG" "$RELEASE_JSON" "$SUMS"',
'gh release upload "$STABLE_TAG" "$GTAR" "$GSIG" --clobber --repo "$STABLE_REPO"':'release_upload_retry "$GTAR" "$GSIG"',
'gh release upload "$STABLE_TAG" "$LATEST_NEW" --clobber --repo "$STABLE_REPO"':'release_upload_retry "$LATEST_NEW"',
}
for a,b in repls.items():
    assert a in src,a
    src=src.replace(a,b,1)
Path(sys.argv[2]).write_text(src)
PY
chmod +x "$TMP"
exec /bin/bash "$TMP"
