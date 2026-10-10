#!/bin/bash
set -Eeuo pipefail

REPORT="$RUNNER_TEMP/endlume-phase2-manual-owner"
SRC="$RUNNER_TEMP/phase2-manual-source"
UNPACK="$RUNNER_TEMP/phase2-manual-unpack"
DMG="$RUNNER_TEMP/ENDLUME-CANONICAL-QA.dmg"
MOUNT="/Volumes/ENDLUME_CANONICAL_QA"
QA_APP="$MOUNT/ENDLUME-CANONICAL-GOOD-PRODUCT-QA.app"
OWNER_APP="/Applications/ENDLUME YT Studio PEISOV.app"
DONE_SENTINEL="/tmp/ENDLUME_PHASE2_OWNER_QA_DONE"
FAIL_SENTINEL="/tmp/ENDLUME_PHASE2_LICENSE_FAIL"
EXPECTED_VERSION="10.0.11"
EXPECTED_BUNDLE_ID="studio.endlume.desktop"
MOUNT_OWNED=NO

rm -rf "$REPORT" "$SRC" "$UNPACK" "$DMG"
mkdir -p "$REPORT" "$SRC" "$UNPACK"
rm -f "$DONE_SENTINEL" "$FAIL_SENTINEL"

cleanup() {
  set +e
  if [ "$MOUNT_OWNED" = YES ] && /sbin/mount | grep -Fq " on $MOUNT "; then
    hdiutil detach -quiet "$MOUNT" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

test "$RUNNER_NAME" = "kirill-mac-endlume"
test -d "$OWNER_APP"
OWNER_EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$OWNER_APP/Contents/Info.plist")"
OWNER_BIN="$OWNER_APP/Contents/MacOS/$OWNER_EXE"
OWNER_SHA_BEFORE="$(shasum -a 256 "$OWNER_BIN" | awk '{print $1}')"
test "$OWNER_SHA_BEFORE" = "$OWNER_APP_BIN_SHA256"

CACHE="$HOME/Library/Caches/endlume-phase2/ENDLUME-CANONICAL-GOOD-PRODUCT-QA.app.zip"
test -f "$CACHE"
ZIP_SHA="$(shasum -a 256 "$CACHE" | awk '{print $1}')"
test "$ZIP_SHA" = "$EXPECTED_APP_ZIP_SHA256"
cp -f "$CACHE" "$SRC/ENDLUME-CANONICAL-GOOD-PRODUCT-QA.app.zip"
ditto -x -k "$SRC/ENDLUME-CANONICAL-GOOD-PRODUCT-QA.app.zip" "$UNPACK"
BUILT_APP="$(find "$UNPACK" -maxdepth 2 -type d -name '*.app' -print -quit)"
test -n "$BUILT_APP"
EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$BUILT_APP/Contents/Info.plist")"
BUILT_BIN="$BUILT_APP/Contents/MacOS/$EXE"
BIN_SHA="$(shasum -a 256 "$BUILT_BIN" | awk '{print $1}')"
test "$BIN_SHA" = "$EXPECTED_APP_BIN_SHA256"
BUNDLE_ID="$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$BUILT_APP/Contents/Info.plist")"
VERSION="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$BUILT_APP/Contents/Info.plist")"
test "$BUNDLE_ID" = "$EXPECTED_BUNDLE_ID"
test "$VERSION" = "$EXPECTED_VERSION"
/usr/bin/codesign --verify --deep --strict "$BUILT_APP"

verify_mounted_candidate() {
  test -d "$QA_APP"
  local qe qb qv qsha
  qe="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$QA_APP/Contents/Info.plist")"
  qb="$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$QA_APP/Contents/Info.plist")"
  qv="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$QA_APP/Contents/Info.plist")"
  qsha="$(shasum -a 256 "$QA_APP/Contents/MacOS/$qe" | awk '{print $1}')"
  test "$qb" = "$EXPECTED_BUNDLE_ID"
  test "$qv" = "$EXPECTED_VERSION"
  test "$qsha" = "$EXPECTED_APP_BIN_SHA256"
  /usr/bin/codesign --verify --deep --strict "$QA_APP"
}

# Manual QA volume preparation only. No app launch, no GUI discovery.
if /sbin/mount | grep -Fq " on $MOUNT "; then
  test -w "$MOUNT" || { echo "BLOCKED_QA_MOUNT_NOT_WRITABLE=YES" >&2; exit 93; }
  if [ -d "$QA_APP" ]; then rm -rf "$QA_APP"; fi
  ditto "$BUILT_APP" "$QA_APP"
  verify_mounted_candidate
  echo "POPULATED_EXISTING_QA_MOUNT=YES"
else
  mkdir -p "$MOUNT"
  hdiutil create -quiet -size 350m -fs APFS -volname ENDLUME_CANONICAL_QA "$DMG"
  hdiutil attach -quiet -nobrowse -mountpoint "$MOUNT" "$DMG"
  MOUNT_OWNED=YES
  ditto "$BUILT_APP" "$QA_APP"
  verify_mounted_candidate
  echo "PREPARED_NEW_QA_MOUNT=YES"
fi

cat > "$REPORT/manual-acceptance-report.txt" <<EOF
ENDLUME PHASE 2 — MANUAL OWNER FOREGROUND UI ACCEPTANCE
DATE=2026-10-10
OWNER_MACHINE=MacBook-Air-Kirill
CANONICAL_PRODUCT_SHA=3f06c7329bd3821bc160e6d88c5b294fc0d82c2b
APP_ZIP_SHA256=$ZIP_SHA
APP_BIN_SHA256=$BIN_SHA
BUNDLE_ID=$BUNDLE_ID
VERSION=$VERSION
CODESIGN=PASS
OWNER_PRODUCTION_APP_SHA256_BEFORE=$OWNER_SHA_BEFORE
OWNER_APPLICATION_REPLACED=PENDING_POSTCHECK
OWNER_STATE=PENDING_OWNER_CONFIRMATION
LICENSE=PENDING_OWNER_CONFIRMATION
GOOGLE_YOUTUBE=PENDING_OWNER_CONFIRMATION
PROJECT=PENDING
EFFECTS_TOGGLE=PENDING
EFFECTS_EDITOR=PENDING
SUBSCRIBE_TOGGLE=PENDING
SUBSCRIBE_EDITOR=PENDING
PREVIEW=PENDING
RENDER_CENTER=PENDING
LIBRARY=PENDING
SETTINGS_GENERAL=PENDING
SETTINGS_FAST_ENGINE=PENDING
SETTINGS_UPDATES=PENDING
SETTINGS_ABOUT=PENDING
MODERN_ICON=PENDING
PHASE_2_FULL_UI_ACCEPTANCE=PENDING_OWNER_CONFIRMATION
FAST_ENGINE_MERGED=NO
STABLE_UNTOUCHED=YES
UPDATER_UNTOUCHED=YES
RELEASE_BLOCKED=YES
EOF

printf '%s\n' \
  'OWNER_MANUAL_ACTION_REQUIRED=YES' \
  'OWNER_COMMAND:' \
  'open -n "/Volumes/ENDLUME_CANONICAL_QA/ENDLUME-CANONICAL-GOOD-PRODUCT-QA.app"' \
  'IF ACTIVATION SCREEN APPEARS: close candidate and run: touch /tmp/ENDLUME_PHASE2_LICENSE_FAIL' \
  'AFTER MANUAL QA: close candidate, confirm Google/YouTube still signed in, then run: touch /tmp/ENDLUME_PHASE2_OWNER_QA_DONE'

RESULT=""
for _ in $(seq 1 2700); do
  if [ -f "$FAIL_SENTINEL" ]; then RESULT="LICENSE_FAIL"; break; fi
  if [ -f "$DONE_SENTINEL" ]; then RESULT="OWNER_DONE"; break; fi
  sleep 1
done

if [ -z "$RESULT" ]; then echo "OWNER_MANUAL_QA_TIMEOUT=YES" >&2; exit 94; fi

OWNER_SHA_AFTER="$(shasum -a 256 "$OWNER_BIN" | awk '{print $1}')"
test "$OWNER_SHA_AFTER" = "$OWNER_APP_BIN_SHA256"
{
  echo "OWNER_PRODUCTION_APP_SHA256_AFTER=$OWNER_SHA_AFTER"
  echo "OWNER_APPLICATION_REPLACED=NO"
  echo "FAST_ENGINE_MERGED=NO"
  echo "STABLE_UNTOUCHED=YES"
  echo "UPDATER_UNTOUCHED=YES"
  echo "RELEASE_BLOCKED=YES"
} >> "$REPORT/manual-acceptance-report.txt"

if [ "$RESULT" = "LICENSE_FAIL" ]; then
  echo "LICENSED_SESSION=FAIL" >> "$REPORT/manual-acceptance-report.txt"
  echo "LICENSED_SESSION=FAIL"
  exit 75
fi

{
  echo "OWNER_MANUAL_QA_COMPLETED=YES"
  echo "OWNER_STATE=PRESERVED_BY_OWNER_CONFIRMATION"
  echo "LICENSE=PRESERVED_BY_OWNER_CONFIRMATION"
  echo "GOOGLE_YOUTUBE=PRESERVED_BY_OWNER_CONFIRMATION"
  echo "LICENSED_SESSION=PASS_BY_OWNER_CONFIRMATION"
  echo "PHASE_2_DECISION=PENDING_SCREENSHOT_REVIEW_OR_OWNER_SCREEN_CONFIRMATION"
} >> "$REPORT/manual-acceptance-report.txt"

echo "OWNER_MANUAL_QA_COMPLETED=YES"
echo "OWNER_APPLICATION_REPLACED=NO"
echo "PHASE_2_DECISION=PENDING_SCREENSHOT_REVIEW_OR_OWNER_SCREEN_CONFIRMATION"
