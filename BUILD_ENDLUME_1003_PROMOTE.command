#!/bin/bash
set -Eeuo pipefail

: "${ENDLUME_RELEASE_ARTIFACT_DIR:?ENDLUME_RELEASE_ARTIFACT_DIR missing}"
: "${ENDLUME_RELEASE_VERSION:?ENDLUME_RELEASE_VERSION missing}"
: "${TAURI_SIGNING_PRIVATE_KEY_PATH:?TAURI_SIGNING_PRIVATE_KEY_PATH missing}"

[[ "$ENDLUME_RELEASE_VERSION" == "10.0.3" ]] || { echo "unexpected version: $ENDLUME_RELEASE_VERSION" >&2; exit 1; }

HOST_REPO="ScaleUPPeisov/scaleup-site"
TAG="endlume-stable"
MAC_ZIP="ENDLUME-YT-Studio-PEISOV-10.0.3-macOS-ARM64.zip"
MAC_TAR="ENDLUME-YT-Studio-PEISOV-10.0.3-macOS-ARM64.app.tar.gz"
WIN_EXE="ENDLUME-YT-Studio-PEISOV-Setup-10.0.3-x64.exe"
ART="$ENDLUME_RELEASE_ARTIFACT_DIR"
TMP="$ART/promote-1003"

rm -rf "$TMP"
mkdir -p "$TMP" "$ART"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.cargo/bin:/usr/bin:/bin:/usr/sbin:/sbin"

command -v gh >/dev/null
command -v npx >/dev/null

echo "Downloading existing 10.0.3 packages..."
gh release download "$TAG" --repo "$HOST_REPO" --dir "$TMP" --pattern "$MAC_ZIP" --clobber
gh release download "$TAG" --repo "$HOST_REPO" --dir "$TMP" --pattern "$WIN_EXE" --clobber

test -s "$TMP/$MAC_ZIP"
test -s "$TMP/$WIN_EXE"

python3 - "$TMP/$WIN_EXE" <<'PY'
import sys
p=sys.argv[1]
with open(p,'rb') as f: assert f.read(2)==b'MZ'
print('WINDOWS_PE_GREEN')
PY

mkdir -p "$TMP/mac-unpack"
/usr/bin/ditto -x -k "$TMP/$MAC_ZIP" "$TMP/mac-unpack"
APP="$(find "$TMP/mac-unpack" -maxdepth 3 -type d -name '*.app' -print -quit)"
test -n "$APP" -a -d "$APP"
BID="$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$APP/Contents/Info.plist")"
VER="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$APP/Contents/Info.plist")"
EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$APP/Contents/Info.plist")"
test "$BID" = "studio.endlume.desktop"
test "$VER" = "10.0.3"
/usr/bin/lipo -archs "$APP/Contents/MacOS/$EXE" | grep -qw arm64
/usr/bin/codesign --verify --deep --strict "$APP"

MAC_OUT="$ART/$MAC_TAR"
/usr/bin/tar -czf "$MAC_OUT" -C "$(dirname "$APP")" "$(basename "$APP")"
test -s "$MAC_OUT"

export TAURI_SIGNING_PRIVATE_KEY_PATH
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD=""
unset TAURI_SIGNING_PRIVATE_KEY || true

npx --yes @tauri-apps/cli@2.10.1 signer sign "$MAC_OUT"
test -s "$MAC_OUT.sig"

WIN_LOCAL="$TMP/$WIN_EXE"
npx --yes @tauri-apps/cli@2.10.1 signer sign "$WIN_LOCAL"
test -s "$WIN_LOCAL.sig"

gh release upload "$TAG" "$WIN_LOCAL.sig" --clobber --repo "$HOST_REPO"

WIN_SIG="$(tr -d '\r\n' < "$WIN_LOCAL.sig")"
WIN_SHA="$(shasum -a 256 "$WIN_LOCAL" | awk '{print $1}')"
WIN_URL="https://github.com/$HOST_REPO/releases/download/$TAG/$WIN_EXE"

python3 - "$ART/windows-platform.json" "$WIN_URL" "$WIN_SIG" "$WIN_SHA" <<'PY'
import json,sys
out,url,sig,sha=sys.argv[1:]
json.dump({'url':url,'signature':sig,'sha256':sha},open(out,'w'),ensure_ascii=False,indent=2)
PY

echo "ENDLUME_1003_PROMOTION_BUILDER_GREEN"
