#!/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
REQ="updates/github/build-request.json"
KEY="$HOME/.endlume-updater/endlume.key"
PUB="$KEY.pub"
HOST_REPO="ScaleUPPeisov/scaleup-site"
TAG="endlume-stable"
ART="${TMPDIR:-/tmp}/endlume-github-release-${RANDOM}-mac"
rm -rf "$ART"; mkdir -p "$ART"

command -v gh >/dev/null 2>&1 || { echo 'gh missing' >&2; exit 1; }
gh auth status -h github.com >/dev/null 2>&1 || { echo 'gh not authenticated' >&2; exit 1; }
[[ -s "$KEY" && -s "$PUB" ]] || { echo "Tauri signing key missing: $KEY" >&2; exit 1; }

python3 - "$REQ" <<'PY'
import json,sys,os
r=json.load(open(sys.argv[1]))
if not r.get('enabled'): raise SystemExit('release request disabled')
b=os.path.basename(str(r.get('builder','')))
if b!=r.get('builder') or not b.startswith('BUILD_ENDLUME_') or not b.endswith('.command'): raise SystemExit('unsafe builder')
PY
VERSION="$(python3 -c 'import json;print(json.load(open("updates/github/build-request.json"))["version"])')"
BUILDER="$(python3 -c 'import json;print(json.load(open("updates/github/build-request.json"))["builder"])')"
NOTES="$(python3 -c 'import json;print(json.load(open("updates/github/build-request.json")).get("notes",""))')"
[[ -f "$BUILDER" ]] || { echo "Builder missing: $BUILDER" >&2; exit 1; }

unset TAURI_SIGNING_PRIVATE_KEY || true
export TAURI_SIGNING_PRIVATE_KEY_PATH="$KEY"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD=""
export ENDLUME_RELEASE_ARTIFACT_DIR="$ART"
export ENDLUME_RELEASE_PLATFORM="darwin-aarch64"
export ENDLUME_RELEASE_VERSION="$VERSION"
export ENDLUME_UPDATER_PUBLIC_KEY_FILE="$PUB"
export ENDLUME_UPDATER_ENDPOINT="https://github.com/$HOST_REPO/releases/download/$TAG/latest.json"
/bin/bash "$BUILDER"

ASSET="$(find "$ART" -maxdepth 8 -type f -name '*.app.tar.gz' -print -quit)"
[[ -n "$ASSET" && -f "$ASSET" ]] || { echo "No macOS updater artifact in $ART" >&2; find "$ART" -type f -print; exit 1; }
SIG_FILE="$ASSET.sig"
[[ -s "$SIG_FILE" ]] || { echo "Signature missing: $SIG_FILE" >&2; exit 1; }
SIG="$(tr -d '\r\n' < "$SIG_FILE")"

FIXED="$ART/ENDLUME-macos-aarch64.app.tar.gz"
FIXED_SIG="$FIXED.sig"
if [[ "$ASSET" != "$FIXED" ]]; then cp "$ASSET" "$FIXED"; fi
printf '%s\n' "$SIG" > "$FIXED_SIG"
ASSET_URL="https://github.com/$HOST_REPO/releases/download/$TAG/$(basename "$FIXED")"

LATEST="$ART/latest.json"
OLD="$ART/old-latest.json"
if gh release download "$TAG" --repo "$HOST_REPO" --pattern latest.json --output "$OLD" >/dev/null 2>&1; then :; else printf '{}\n' > "$OLD"; fi
python3 - "$OLD" "$LATEST" "$VERSION" "$NOTES" "$ASSET_URL" "$SIG" <<'PY'
import json,sys,datetime
old,out,version,notes,url,sig=sys.argv[1:]
try: d=json.load(open(old))
except: d={}
platforms=d.get('platforms') if isinstance(d.get('platforms'),dict) else {}
platforms['darwin-aarch64']={'url':url,'signature':sig}
obj={'version':version,'notes':notes,'pub_date':datetime.datetime.now(datetime.timezone.utc).isoformat(),'platforms':platforms}
json.dump(obj,open(out,'w'),ensure_ascii=False,indent=2)
PY

if ! gh release view "$TAG" --repo "$HOST_REPO" >/dev/null 2>&1; then
  gh release create "$TAG" --repo "$HOST_REPO" --title "ENDLUME Stable Updates" --notes "Signed updater channel for ENDLUME Studio. No GitHub Actions are used."
fi

gh release upload "$TAG" "$FIXED" "$FIXED_SIG" "$LATEST" --clobber --repo "$HOST_REPO"
echo "ENDLUME $VERSION macOS published"
echo "Updater: https://github.com/$HOST_REPO/releases/download/$TAG/latest.json"

# One-time bridge: existing 8.38/8.39 builds do not know the new static endpoint.
# Only 8.40 is bootstrap-installed. 8.41+ must use the native in-app updater.
if [[ "$VERSION" == "1.0.0-alpha.8.40" ]]; then
  DEST="/Applications/ENDLUME Studio.app"
  CUR=""
  if [[ -f "$DEST/Contents/Info.plist" ]]; then
    CUR="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$DEST/Contents/Info.plist" 2>/dev/null || true)"
  fi
  if [[ "$CUR" != "$VERSION" ]]; then
    echo "Bootstrap install: $CUR -> $VERSION"
    [[ -w /Applications ]] || { echo '/Applications is not writable for bootstrap install' >&2; exit 1; }
    INST="$ART/bootstrap-install"
    rm -rf "$INST"; mkdir -p "$INST"
    /usr/bin/tar -xzf "$FIXED" -C "$INST"
    NEW_APP="$(find "$INST" -maxdepth 3 -type d -name 'ENDLUME Studio.app' -print -quit)"
    [[ -n "$NEW_APP" && -d "$NEW_APP" ]] || { echo 'bootstrap archive has no ENDLUME Studio.app' >&2; exit 1; }
    BID="$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$NEW_APP/Contents/Info.plist")"
    VER="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$NEW_APP/Contents/Info.plist")"
    [[ "$BID" == 'studio.endlume.desktop' ]] || { echo "bootstrap Bundle ID mismatch: $BID" >&2; exit 1; }
    [[ "$VER" == "$VERSION" ]] || { echo "bootstrap version mismatch: $VER" >&2; exit 1; }
    /usr/bin/codesign --verify --deep --strict "$NEW_APP" >/dev/null 2>&1 || /usr/bin/codesign --force --deep --sign - "$NEW_APP"
    /usr/bin/codesign --verify --deep --strict "$NEW_APP" >/dev/null 2>&1 || { echo 'bootstrap app codesign invalid' >&2; exit 1; }
    NEW="/Applications/.ENDLUME Studio.8.40.new.app"
    OLD_APP="/Applications/.ENDLUME Studio.bootstrap.previous.app"
    rm -rf "$NEW" "$OLD_APP"
    /usr/bin/ditto "$NEW_APP" "$NEW"
    /usr/bin/osascript -e 'tell application "ENDLUME Studio" to quit' >/dev/null 2>&1 || true
    sleep 1
    /usr/bin/pkill -x 'ENDLUME Studio' >/dev/null 2>&1 || true
    if [[ -d "$DEST" ]]; then /bin/mv "$DEST" "$OLD_APP"; fi
    if /bin/mv "$NEW" "$DEST"; then :; else
      [[ -d "$OLD_APP" ]] && /bin/mv "$OLD_APP" "$DEST"
      echo 'bootstrap atomic install failed; previous app restored' >&2
      exit 1
    fi
    FINAL="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$DEST/Contents/Info.plist" 2>/dev/null || true)"
    if [[ "$FINAL" != "$VERSION" ]]; then
      rm -rf "$DEST"
      [[ -d "$OLD_APP" ]] && /bin/mv "$OLD_APP" "$DEST"
      echo "bootstrap final version mismatch: $FINAL; rollback done" >&2
      exit 1
    fi
    /usr/bin/xattr -dr com.apple.quarantine "$DEST" >/dev/null 2>&1 || true
    rm -rf "$OLD_APP"
    /usr/bin/open "$DEST" >/dev/null 2>&1 || true
    echo "✅ ENDLUME 8.40 bootstrap-installed; future updates are native in-app"
  else
    echo "ENDLUME 8.40 already installed; bootstrap skipped"
  fi
fi
