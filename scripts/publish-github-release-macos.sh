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
forced=os.environ.get('ENDLUME_FORCE_RELEASE')=='1'
if not r.get('enabled') and not forced:
    raise SystemExit('release request disabled')
b=os.path.basename(str(r.get('builder','')))
if b!=r.get('builder') or not b.startswith('BUILD_ENDLUME_') or not b.endswith('.command'): raise SystemExit('unsafe builder')
print('release mode: FORCE foreground' if forced else 'release mode: background agent')
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
[[ -n "$SIG" ]] || { echo 'Updater signature is empty' >&2; exit 1; }

FIXED="$ART/ENDLUME-macos-aarch64.app.tar.gz"
FIXED_SIG="$FIXED.sig"
if [[ "$ASSET" != "$FIXED" ]]; then cp "$ASSET" "$FIXED"; fi
printf '%s\n' "$SIG" > "$FIXED_SIG"
ASSET_URL="https://github.com/$HOST_REPO/releases/download/$TAG/$(basename "$FIXED")"

LATEST="$ART/latest.json"
OLD="$ART/old-latest.json"
if gh release download "$TAG" --repo "$HOST_REPO" --pattern latest.json --output "$OLD" >/dev/null 2>&1; then :; else printf '{}\n' > "$OLD"; fi
WINDOWS_META="$ART/windows-platform.json"
python3 - "$OLD" "$LATEST" "$VERSION" "$NOTES" "$ASSET_URL" "$SIG" "$WINDOWS_META" <<'PY'
import json,sys,datetime,pathlib
old,out,version,notes,url,sig,windows_meta=sys.argv[1:]
try: d=json.load(open(old))
except: d={}
platforms=d.get('platforms') if isinstance(d.get('platforms'),dict) else {}
platforms['darwin-aarch64']={'url':url,'signature':sig}
wm=pathlib.Path(windows_meta)
if wm.is_file():
    w=json.loads(wm.read_text())
    assert w.get('url') and w.get('signature'),'invalid windows updater metadata'
    platforms['windows-x86_64']=w
obj={'version':version,'notes':notes,'pub_date':datetime.datetime.now(datetime.timezone.utc).isoformat(),'platforms':platforms}
json.dump(obj,open(out,'w'),ensure_ascii=False,indent=2)
PY

# Validate the exact static JSON contract BEFORE upload.
python3 - "$LATEST" "$VERSION" "$ASSET_URL" <<'PY'
import json,sys
path,version,url=sys.argv[1:]
d=json.load(open(path))
assert d.get('version')==version,(d.get('version'),version)
p=d.get('platforms',{}).get('darwin-aarch64')
assert isinstance(p,dict),'darwin-aarch64 platform missing'
assert p.get('url')==url,(p.get('url'),url)
assert isinstance(p.get('signature'),str) and p['signature'].strip(),'signature empty'
print('PASS: latest.json static updater contract valid')
PY

if ! gh release view "$TAG" --repo "$HOST_REPO" >/dev/null 2>&1; then
  gh release create "$TAG" --repo "$HOST_REPO" --title "ENDLUME Stable Updates" --notes "Signed updater channel for ENDLUME Studio. No GitHub Actions are used."
fi

gh release upload "$TAG" "$FIXED" "$FIXED_SIG" "$LATEST" --clobber --repo "$HOST_REPO"

# CRITICAL: never report success while the public release is empty/incomplete.
RELEASE_JSON="$ART/release.json"
gh api "/repos/$HOST_REPO/releases/tags/$TAG" > "$RELEASE_JSON"
python3 - "$RELEASE_JSON" "$VERSION" <<'PY'
import json,sys
path,version=sys.argv[1:]
d=json.load(open(path))
names={x.get('name') for x in d.get('assets',[])}
required={'latest.json','ENDLUME-macos-aarch64.app.tar.gz','ENDLUME-macos-aarch64.app.tar.gz.sig'}
missing=required-names
if missing: raise SystemExit('Published release assets missing: '+', '.join(sorted(missing)))
print('PASS: GitHub release contains latest.json + app.tar.gz + sig')
PY

# Download the just-published JSON through the public release URL and validate it
# again. This catches HTML/redirect/empty-asset mistakes before the agent records success.
PUBLIC_LATEST="$ART/public-latest.json"
/usr/bin/curl -fL --retry 3 --connect-timeout 10 --max-time 30 \
  "https://github.com/$HOST_REPO/releases/download/$TAG/latest.json" -o "$PUBLIC_LATEST"
python3 - "$PUBLIC_LATEST" "$VERSION" <<'PY'
import json,sys
path,version=sys.argv[1:]
d=json.load(open(path))
assert d.get('version')==version,(d.get('version'),version)
p=d.get('platforms',{}).get('darwin-aarch64')
assert isinstance(p,dict) and p.get('url','').startswith('https://github.com/'),'public updater URL invalid'
assert isinstance(p.get('signature'),str) and p['signature'].strip(),'public signature empty'
print('PASS: public latest.json is downloadable and valid')
PY

echo "✅ ENDLUME $VERSION macOS PUBLISHED ONLINE"
echo "Updater: https://github.com/$HOST_REPO/releases/download/$TAG/latest.json"

# Legacy one-time bootstrap retained only for historical 8.40 publisher calls.
# 8.41+ NEVER installs directly here; installed 8.40 uses native Tauri updater.
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
