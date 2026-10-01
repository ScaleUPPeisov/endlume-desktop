#!/bin/bash
set -Eeuo pipefail

: "${ENDLUME_RELEASE_ARTIFACT_DIR:?ENDLUME_RELEASE_ARTIFACT_DIR missing}"
: "${ENDLUME_RELEASE_VERSION:?ENDLUME_RELEASE_VERSION missing}"
: "${TAURI_SIGNING_PRIVATE_KEY_PATH:?TAURI_SIGNING_PRIVATE_KEY_PATH missing}"

VERSION="10.0.6"
SOURCE_BRANCH="release-prep/endlume-10.0.6-production-hotfix-final"
SOURCE_HEAD="bd81d86152cb2f20fe02e33849aec255ea013634"
HOTFIX_SHA="03df61a58641d5ce0b4e1c432c99af935acbf4d1"
HOST_REPO="ScaleUPPeisov/scaleup-site"
TAG="endlume-stable"
LEGACY_MAC_ZIP="ENDLUME-YT-Studio-PEISOV-10.0.3-macOS-ARM64.zip"
CLEAN_ZIP="ENDLUME-YT-Studio-PEISOV-10.0.6-macOS-ARM64.zip"

[[ "$ENDLUME_RELEASE_VERSION" == "$VERSION" ]] || {
  echo "unexpected version: $ENDLUME_RELEASE_VERSION" >&2
  exit 1
}

ROOT="$(cd "$(dirname "$0")" && pwd)"
ART="$ENDLUME_RELEASE_ARTIFACT_DIR"
TMP="$(mktemp -d /tmp/endlume-1006-updater.XXXXXX)"
WORK="$TMP/source"
LEGACY="$TMP/legacy"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT

export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.cargo/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME
mkdir -p "$ART" "$WORK" "$LEGACY"

command -v git >/dev/null
command -v gh >/dev/null
command -v node >/dev/null
command -v npm >/dev/null
command -v cargo >/dev/null
command -v npx >/dev/null
gh auth status -h github.com >/dev/null

echo "1/8 Fetch exact ENDLUME 10.0.6 source"
cd "$ROOT"
git fetch --no-tags origin "$SOURCE_BRANCH"
FETCHED="$(git rev-parse FETCH_HEAD)"
[[ "$FETCHED" == "$SOURCE_HEAD" ]] || {
  echo "release HEAD mismatch: expected=$SOURCE_HEAD got=$FETCHED" >&2
  exit 20
}
git merge-base --is-ancestor "$HOTFIX_SHA" "$SOURCE_HEAD" || {
  echo "hotfix is not ancestor of release head" >&2
  exit 21
}
git archive "$SOURCE_HEAD" | /usr/bin/tar -x -C "$WORK"

python3 - "$WORK" <<'PY'
import json,re,sys
from pathlib import Path
w=Path(sys.argv[1])
v='10.0.6'
assert json.loads((w/'package.json').read_text())['version']==v
assert json.loads((w/'package-lock.json').read_text())['version']==v
cfg=json.loads((w/'src-tauri/tauri.conf.json').read_text())
assert cfg['version']==v
assert cfg['identifier']=='studio.endlume.desktop'
assert cfg['app']['windows'] and any(x.get('label')=='main' for x in cfg['app']['windows'])
cargo=(w/'src-tauri/Cargo.toml').read_text()
assert re.search(r'^version\s*=\s*"10[.]0[.]6"$',cargo,re.M)
print('ENDLUME_1006_EXACT_SOURCE_GREEN')
PY

echo "2/8 Restore proven portable macOS FFmpeg sidecars"
cd "$LEGACY"
gh release download "$TAG" --repo "$HOST_REPO" --pattern "$LEGACY_MAC_ZIP" --clobber
test -s "$LEGACY/$LEGACY_MAC_ZIP"
/usr/bin/ditto -x -k "$LEGACY/$LEGACY_MAC_ZIP" "$LEGACY/unpack"
OLD_APP="$(find "$LEGACY/unpack" -maxdepth 3 -type d -name '*.app' -print -quit)"
test -n "$OLD_APP" -a -d "$OLD_APP"
test -x "$OLD_APP/Contents/MacOS/ffmpeg"
test -x "$OLD_APP/Contents/MacOS/ffprobe"
mkdir -p "$WORK/src-tauri/binaries"
cp "$OLD_APP/Contents/MacOS/ffmpeg" "$WORK/src-tauri/binaries/ffmpeg-aarch64-apple-darwin"
cp "$OLD_APP/Contents/MacOS/ffprobe" "$WORK/src-tauri/binaries/ffprobe-aarch64-apple-darwin"
chmod 755 "$WORK/src-tauri/binaries/ffmpeg-aarch64-apple-darwin" "$WORK/src-tauri/binaries/ffprobe-aarch64-apple-darwin"
file "$WORK/src-tauri/binaries/ffmpeg-aarch64-apple-darwin" | grep -E 'arm64|Mach-O'
file "$WORK/src-tauri/binaries/ffprobe-aarch64-apple-darwin" | grep -E 'arm64|Mach-O'
"$WORK/src-tauri/binaries/ffmpeg-aarch64-apple-darwin" -hide_banner -filters 2>/dev/null | grep -q acrossfade
"$WORK/src-tauri/binaries/ffprobe-aarch64-apple-darwin" -version >/dev/null
echo ENDLUME_1006_PORTABLE_FFMPEG_GREEN

echo "3/8 Compile release"
cd "$WORK"
rustup target add aarch64-apple-darwin >/dev/null 2>&1 || true
npm ci
npm run check
npm run build
cargo check --manifest-path src-tauri/Cargo.toml --target aarch64-apple-darwin

python3 - <<'PY'
import json
from pathlib import Path
p=Path('src-tauri/tauri.conf.json')
d=json.loads(p.read_text())
d['bundle']['createUpdaterArtifacts']=False
assert d['app']['windows'] and any(w.get('label')=='main' for w in d['app']['windows'])
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
PY

echo "4/8 Build macOS ARM64 app"
export CARGO_TARGET_DIR="$HOME/.endlume-build-cache/target-1006-local-updater"
rm -rf "$CARGO_TARGET_DIR/aarch64-apple-darwin/release/bundle/macos"
npm run tauri build -- --target aarch64-apple-darwin --bundles app
APP="$(find "$CARGO_TARGET_DIR" -type d -path '*/aarch64-apple-darwin/release/bundle/macos/*.app' -print -quit)"
test -n "$APP" -a -d "$APP"

BID="$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$APP/Contents/Info.plist")"
VER="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$APP/Contents/Info.plist")"
EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$APP/Contents/Info.plist")"
test "$BID" = "studio.endlume.desktop"
test "$VER" = "$VERSION"
/usr/bin/lipo -archs "$APP/Contents/MacOS/$EXE" | grep -qw arm64
test -x "$APP/Contents/MacOS/ffmpeg"
test -x "$APP/Contents/MacOS/ffprobe"

echo "5/8 Seal app"
IDENTITIES="$(/usr/bin/security find-identity -v -p codesigning 2>&1 || true)"
IDENTITY="$(printf '%s\n' "$IDENTITIES" | grep 'Developer ID Application:' | head -1 | sed -E 's/.*"([^"]+)".*/\1/' || true)"
if [[ -n "$IDENTITY" ]]; then
  /usr/bin/codesign --force --deep --options runtime --timestamp --sign "$IDENTITY" "$APP"
  echo "ENDLUME_1006_DEVELOPER_ID_SIGNED=$IDENTITY"
else
  /usr/bin/codesign --force --deep --sign - "$APP"
  echo "ENDLUME_1006_ADHOC_SIGNED"
fi
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP"
test -s "$APP/Contents/_CodeSignature/CodeResources"

if /usr/bin/xcrun stapler validate "$APP" >/dev/null 2>&1; then
  echo ENDLUME_1006_NOTARIZATION_ALREADY_GREEN
elif [[ -n "${APPLE_ID:-}" && -n "${APPLE_PASSWORD:-}" && -n "${APPLE_TEAM_ID:-}" ]]; then
  NOTARY_ZIP="$TMP/notary.zip"
  /usr/bin/ditto -c -k --sequesterRsrc --keepParent "$APP" "$NOTARY_ZIP"
  /usr/bin/xcrun notarytool submit "$NOTARY_ZIP" --apple-id "$APPLE_ID" --password "$APPLE_PASSWORD" --team-id "$APPLE_TEAM_ID" --wait
  /usr/bin/xcrun stapler staple "$APP"
  /usr/bin/xcrun stapler validate "$APP"
  echo ENDLUME_1006_NOTARIZATION_GREEN
elif [[ -n "${APPLE_API_KEY_PATH:-}" && -n "${APPLE_API_KEY:-}" && -n "${APPLE_API_ISSUER:-}" ]]; then
  NOTARY_ZIP="$TMP/notary.zip"
  /usr/bin/ditto -c -k --sequesterRsrc --keepParent "$APP" "$NOTARY_ZIP"
  /usr/bin/xcrun notarytool submit "$NOTARY_ZIP" --key "$APPLE_API_KEY_PATH" --key-id "$APPLE_API_KEY" --issuer "$APPLE_API_ISSUER" --wait
  /usr/bin/xcrun stapler staple "$APP"
  /usr/bin/xcrun stapler validate "$APP"
  echo ENDLUME_1006_NOTARIZATION_GREEN
else
  echo "ENDLUME_1006_NOTARIZATION_NOT_AVAILABLE_LOCALLY"
fi

echo "6/8 Packaged launch + FFmpeg live-preview smoke"
MARKER="$TMP/launch.json"
rm -f "$MARKER"
/bin/launchctl setenv ENDLUME_LAUNCH_SMOKE_MARKER "$MARKER"
/usr/bin/open -n "$APP"
for I in $(seq 1 80); do
  [[ -s "$MARKER" ]] && break
  sleep 0.25
done
/bin/launchctl unsetenv ENDLUME_LAUNCH_SMOKE_MARKER >/dev/null 2>&1 || true
test -s "$MARKER"
PID="$(python3 - "$MARKER" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
assert d.get('label')=='main',d
assert d.get('frontendLoaded') is True,d
print(d['pid'])
PY
)"
kill -0 "$PID"
kill "$PID" >/dev/null 2>&1 || true

ENDLUME_APP_PATH="$APP" node scripts/verify-macos-ffmpeg-bundle.mjs | tee "$TMP/runtime.log"
grep -q ENDLUME_MACOS_FFMPEG_RUNTIME_PASS "$TMP/runtime.log"
grep -q EFFECTS_LIVE_PREVIEW_RUNTIME_PASS "$TMP/runtime.log"
grep -q SUBSCRIBE_LIVE_PREVIEW_RUNTIME_PASS "$TMP/runtime.log"

echo "7/8 Create signed updater"
rm -rf "$ART"
mkdir -p "$ART"
UPDATER="$ART/ENDLUME-macos-aarch64.app.tar.gz"
/usr/bin/tar -czf "$UPDATER" -C "$(dirname "$APP")" "$(basename "$APP")"
test -s "$UPDATER"
export TAURI_SIGNING_PRIVATE_KEY_PATH
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD=""
unset TAURI_SIGNING_PRIVATE_KEY || true
npx --yes @tauri-apps/cli@2.10.1 signer sign "$UPDATER"
test -s "$UPDATER.sig"

VERIFY="$TMP/updater-unpack"
mkdir -p "$VERIFY"
/usr/bin/tar -xzf "$UPDATER" -C "$VERIFY"
VERIFY_APP="$(find "$VERIFY" -maxdepth 2 -type d -name '*.app' -print -quit)"
test -n "$VERIFY_APP" -a -d "$VERIFY_APP"
test "$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$VERIFY_APP/Contents/Info.plist")" = "$VERSION"
/usr/bin/codesign --verify --deep --strict "$VERIFY_APP"
"$VERIFY_APP/Contents/MacOS/ffmpeg" -version >/dev/null
"$VERIFY_APP/Contents/MacOS/ffprobe" -version >/dev/null

echo "8/8 Create clean-install ZIP + checksums"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$APP" "$ART/$CLEAN_ZIP"
shasum -a 256 "$ART/$CLEAN_ZIP" > "$ART/$CLEAN_ZIP.sha256"
shasum -a 256 "$UPDATER" > "$UPDATER.sha256"
printf '%s\n' "$VERSION" > "$ART/version.txt"

echo "ENDLUME_1006_LOCAL_UPDATER_BUILDER_GREEN"
echo "MAC_UPDATER_SHA256=$(shasum -a 256 "$UPDATER" | awk '{print $1}')"
echo "MAC_CLEAN_SHA256=$(shasum -a 256 "$ART/$CLEAN_ZIP" | awk '{print $1}')"
