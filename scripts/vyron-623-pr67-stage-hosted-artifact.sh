#!/bin/bash
# Stages an artifact from the one pinned successful GitHub-hosted build.
# Only PUBLIC updater key material is parsed. Does not read Keychain or OAuth.
set -Eeuo pipefail
umask 077
test "$RUNNER_NAME" = kirill-mac-endlume
test "$(uname -m)" = arm64
test -n "$GH_TOKEN"
SOURCE=b11510b4de6f6613f1cd82c8c79e1395b439b6ae
BUILD_SHA=7805cf0c039c5334b4438e649c7268519fc7ac25
PIN=1c97657fd2a7ba4c2a0ce5b5361518eeacf76da274521b1977d57a55b8dbcec9
ART="$RUNNER_TEMP/pr67-623-download"
ARCHIVE="$ART/VYRON-PR67-6.1.23-UNSIGNED-NOT-INSTALLABLE.tar.gz"
META="$ART/rc-evidence/STATUS.txt"
SHAFILE="$ART/rc-evidence/executable-sha256.txt"
APPID=studio.channelflow.desktop
test -f "$ARCHIVE" && test -f "$META" && test -f "$SHAFILE"
test "$(stat -f %z "$ARCHIVE")" -lt 1500000000
# Check run provenance before parsing downloaded archive.
RUN_STATUS="$RUNNER_TEMP/pr67-623-build-status.json"
/usr/bin/curl --silent --show-error --fail --retry 2 --max-time 30 \
 -H 'Accept: application/vnd.github+json' \
 -H "Authorization: Bearer $GH_TOKEN" \
 "https://api.github.com/repos/ScaleUPPeisov/endlume-desktop/actions/runs/44892542128" > "$RUN_STATUS"
/usr/bin/python3 - "$RUN_STATUS" "$BUILD_SHA" <<'PY'
import json,sys
o=json.load(open(sys.argv[1]))
assert o['id']==44892542128 and o['status']=='completed' and o['conclusion']=='success'
assert o['head_sha']==sys.argv[2] and o['repository']['full_name']=='ScaleUPPeisov/endlume-desktop'
assert o['path']=='.github/workflows/vyron-pr67-623-pinned-arm64-build.yml'
print('PINNED_HOSTED_BUILD_PROVENANCE=PASS')
PY
rm -f "$RUN_STATUS"
grep -Fxq "source=$SOURCE" "$META"
grep -Fxq 'version=6.1.23' "$META"
grep -Fxq "identity=$APPID" "$META"
grep -Fxq 'arch=arm64' "$META"
grep -Fxq 'signature=NOT_VERIFIED_FOR_DISTRIBUTION' "$META"
grep -Fxq 'notarization=NOT_PERFORMED' "$META"
grep -Fxq 'install=FORBIDDEN' "$META"
grep -Fxq 'stable_feed=UNCHANGED' "$META"
BASE="$HOME/.vyron-owner-rollback"
test -d "$BASE" && test -d "$BASE/pr67-preinstall-pPJL4w"
test -z "$(find "$BASE" -mindepth 1 -maxdepth 1 -type d -name 'staged-623-pr67-hosted-*' -print -quit)"
STAGE="$(mktemp -d "$BASE/staged-623-pr67-hosted-XXXXXX")"
chmod 700 "$STAGE"
# Strictly bounded, path-validated extraction: never let archive escape staging.
export PR67_STAGE="$STAGE"
/usr/bin/python3 - "$ARCHIVE" "$STAGE" <<'PY'
import pathlib,sys,tarfile
archive=pathlib.Path(sys.argv[1])
root=pathlib.Path(sys.argv[2]).resolve()
bundle=root/'VYRON.app'
with tarfile.open(archive,'r:gz') as tf:
  members=tf.getmembers()
  assert 0<len(members)<200000
  total=0
  for m in members:
    p=pathlib.PurePosixPath(m.name)
    assert not p.is_absolute() and p.parts and p.parts[0]=='VYRON.app' and '..' not in p.parts
    assert not (m.isdev() or m.isfifo() or m.isln())
    assert m.isfile() or m.isdir() or m.issym()
    if m.isfile():
      total+=m.size
      assert m.size<1000000000 and total<2000000000
    if m.issym():
      target=(root/pathlib.Path(*p.parts[:-1])/m.linkname).resolve()
      assert target==bundle or bundle in target.parents
  tf.extractall(root)
assert (bundle/'Contents'/'Info.plist').is_file()
print('ARCHIVE_PATH_BOUNDS=PASS')
PY
SRC="$STAGE/VYRON.app"
test -d "$SRC" && test ! -L "$SRC"
plist(){ /usr/libexec/PlistBuddy -c "Print :$2" "$1/Contents/Info.plist"; }
test "$(plist "$SRC" CFBundleShortVersionString)" = 6.1.23
test "$(plist "$SRC" CFBundleIdentifier)" = "$APPID"
EXE="$(plist "$SRC" CFBundleExecutable)"
test "$EXE" = "$(plist /Applications/VYRON.app CFBundleExecutable)"
/usr/bin/lipo -archs "$SRC/Contents/MacOS/$EXE" | tr ' ' '\n' | grep -Fxq arm64
EXE_SHA="$(awk 'NR==1{print $1}' "$SHAFILE")"
test "$EXE_SHA" = "$(shasum -a 256 "$SRC/Contents/MacOS/$EXE" | awk '{print $1}')"
# Inspect actual embedded rotated Tauri key; never access private signing material.
/usr/bin/python3 - "$SRC/Contents/MacOS/$EXE" "$PIN" <<'PY'
import base64,hashlib,re,sys
from pathlib import Path
raw=Path(sys.argv[1]).read_bytes()
pin=sys.argv[2]
hits=set()
for m in re.finditer(rb'dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWdu[0-9A-Za-z+/=]{35,300}',raw):
  s=m.group().decode()
  for end in range(70,len(s)+1):
    try: c=base64.b64decode(s[:end],validate=True).decode()
    except (ValueError,UnicodeError): continue
    lines=c.strip().splitlines()
    if len(lines)!=2 or not lines[0].startswith('untrusted comment: minisign public key: '): continue
    try: pub=base64.b64decode(lines[1],validate=True)
    except ValueError: continue
    if len(pub)==42 and pub[:2]==b'Ed' and hashlib.sha256(pub).hexdigest()==pin: hits.add(pin)
    break
assert hits=={pin},'ROTATED_TAURI_UPDATER_PUBLIC_KEY_NOT_FOUND'
print('ROTATED_UPDATER_PIN=PASS')
PY
if /usr/bin/xattr -p com.apple.quarantine "$SRC" >/dev/null 2>&1 ||
  /usr/bin/xattr -p com.apple.quarantine "$SRC/Contents/MacOS/$EXE" >/dev/null 2>&1; then
  echo 'GATEKEEPER_QUARANTINE_PRESENT_NO_OVERRIDE'; exit 1
fi
# Private local ad-hoc signature: NOT a Tauri updater signature, and NOT public distribution.
/usr/bin/codesign --force --deep --sign - --timestamp=none "$SRC"
/usr/bin/codesign --verify --deep --strict "$SRC"
echo 'PRIVATE_LOCAL_ADHOC_SIGNATURE=PASS'
if /usr/sbin/spctl --assess --type execute --verbose "$SRC" >/dev/null 2>&1; then
  echo 'GATEKEEPER_ASSESS=ACCEPTED'
else
  echo 'GATEKEEPER_ASSESS=REJECTED_NONQUARANTINED_ADHOC'
fi
test ! -e "$STAGE/VERIFIED"
SIGNED_SHA="$(shasum -a 256 "$SRC/Contents/MacOS/$EXE" | awk '{print $1}')"
printf 'source=%s\nversion=6.1.23\napproved_pubkey_sha256=%s\nbootstrap_ad_hoc=YES\nupdater_archive=NOT_SIGNED_NOT_DISTRIBUTABLE\nexecutable_sha256=%s\n' "$SOURCE" "$PIN" "$SIGNED_SHA" > "$STAGE/VERIFIED"
chmod 600 "$STAGE/VERIFIED"
echo 'SIGNED_STAGE_READY=PASS'
echo 'PRODUCTION_UPDATER_FEED=UNCHANGED'
