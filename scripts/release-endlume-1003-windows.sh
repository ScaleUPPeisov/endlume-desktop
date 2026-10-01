#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.cargo/bin:/usr/bin:/bin:/usr/sbin:/sbin"
VERSION="10.0.3"
WINDOWS_TARGET="x86_64-pc-windows-msvc"
WINDOWS_GENERIC_ASSET="ENDLUME-windows-x86_64-setup.exe"
WINDOWS_VERSIONED_ASSET="ENDLUME-YT-Studio-PEISOV-Setup-10.0.3-x64.exe"
STABLE_REPO="ScaleUPPeisov/scaleup-site"
STABLE_TAG="endlume-stable"
STAGE="$RUNNER_TEMP/endlume-1003-windows"
CARGO_TARGET_DIR="$HOME/.endlume-build-cache/target-1003-windows"
export CARGO_TARGET_DIR

test "$(uname -s)" = "Darwin"
test "$(uname -m)" = "arm64"
test -n "${RELEASE_TOKEN:-}"
test -s "$HOME/.endlume-updater/endlume.key"
export GH_TOKEN="$RELEASE_TOKEN"

python3 - <<'PY'
import json,re
from pathlib import Path
v='10.0.3'
m=json.loads(Path('release/endlume-10.0.3-windows.json').read_text())
assert m['enabled'] is True and m['user_release_approval'] is True,m
assert m['version']==v and m['platform']=='windows-x86_64',m
assert json.loads(Path('package.json').read_text())['version']==v
assert json.loads(Path('package-lock.json').read_text())['version']==v
assert json.loads(Path('src-tauri/tauri.conf.json').read_text())['version']==v
assert re.search(r'^version = "10\.0\.3"$',Path('src-tauri/Cargo.toml').read_text(),re.M)
w=json.loads(Path('src-tauri/tauri.windows.conf.json').read_text())
assert w['identifier']=='studio.endlume.desktop'
assert w['bundle']['targets']==['nsis']
assert w['bundle']['windows']['nsis']['installMode']=='currentUser'
print('ENDLUME_1003_WINDOWS_IDENTITY_GREEN')
PY

mkdir -p "$STAGE"
gh api "repos/$STABLE_REPO/releases/tags/$STABLE_TAG" > "$STAGE/release-before.json"
LATEST_ID="$(python3 - "$STAGE/release-before.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
m={a['name']:a for a in r.get('assets',[])}
assert 'latest.json' in m,'latest.json missing'
print(m['latest.json']['id'])
PY
)"
gh api -H 'Accept: application/octet-stream' "repos/$STABLE_REPO/releases/assets/$LATEST_ID" > "$STAGE/latest-mac.json"
python3 - "$STAGE/latest-mac.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
assert d.get('version')=='10.0.3',d
p=d.get('platforms',{}).get('darwin-aarch64')
assert p and p.get('url') and p.get('signature') and p.get('sha256'),d
assert len(p['sha256'])==64,d
print('ENDLUME_1003_MAC_STABLE_PRESENT',p['sha256'])
PY

npm ci
ENDLUME_BUILD_CACHE_KEEP=2 ENDLUME_BUILD_CACHE_MAX_BYTES=12000000000 bash scripts/cleanup-endlume-build-cache.sh

mkdir -p src-tauri/binaries
cp "$(command -v ffmpeg)" src-tauri/binaries/ffmpeg-aarch64-apple-darwin
cp "$(command -v ffprobe)" src-tauri/binaries/ffprobe-aarch64-apple-darwin
chmod +x src-tauri/binaries/ffmpeg-aarch64-apple-darwin src-tauri/binaries/ffprobe-aarch64-apple-darwin

brew list nsis >/dev/null 2>&1 || brew install nsis
brew list llvm >/dev/null 2>&1 || brew install llvm
export PATH="$(brew --prefix llvm)/bin:$HOME/.cargo/bin:/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
rustup target add "$WINDOWS_TARGET"
command -v cargo-xwin >/dev/null 2>&1 || cargo install --locked cargo-xwin

ARCHIVE='ffmpeg-master-latest-win64-gpl.zip'
CACHE="$HOME/.endlume-build-cache/windows-sidecars-1003"
ZIP="$CACHE/$ARCHIVE"
EXTRACT="$CACHE/extract"
mkdir -p "$CACHE" src-tauri/binaries
[ -s "$ZIP" ] || curl -fL --retry 4 --connect-timeout 15 -o "$ZIP" "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/$ARCHIVE"
rm -rf "$EXTRACT"; mkdir -p "$EXTRACT"
ditto -x -k "$ZIP" "$EXTRACT"
FFMPEG="$(find "$EXTRACT" -type f -name ffmpeg.exe -print -quit)"
FFPROBE="$(find "$EXTRACT" -type f -name ffprobe.exe -print -quit)"
test -n "$FFMPEG" -a -s "$FFMPEG"
test -n "$FFPROBE" -a -s "$FFPROBE"
cp "$FFMPEG" "src-tauri/binaries/ffmpeg-$WINDOWS_TARGET.exe"
cp "$FFPROBE" "src-tauri/binaries/ffprobe-$WINDOWS_TARGET.exe"
file "src-tauri/binaries/ffmpeg-$WINDOWS_TARGET.exe" | grep -E 'PE32|MS Windows'
echo ENDLUME_1003_WINDOWS_TOOLCHAIN_GREEN

python3 - <<'PY'
import json
from pathlib import Path
p=Path('src-tauri/tauri.conf.json')
d=json.loads(p.read_text())
assert d['version']=='10.0.3'
d['bundle']['createUpdaterArtifacts']=False
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
print('ENDLUME_1003_WINDOWS_RUNTIME_CONFIG_GREEN')
PY

unset TAURI_SIGNING_PRIVATE_KEY TAURI_SIGNING_PRIVATE_KEY_PATH TAURI_SIGNING_PRIVATE_KEY_PASSWORD || true
NSIS="$CARGO_TARGET_DIR/$WINDOWS_TARGET/release/bundle/nsis"
CAND="$NSIS/ENDLUME YT Studio PEISOV_10.0.3_x64-setup.exe"
if [ -s "$CAND" ]; then
  echo "ENDLUME_1003_WINDOWS_REUSE_NSIS=$CAND"
else
  npm run tauri build -- --runner cargo-xwin --target "$WINDOWS_TARGET" --bundles nsis --config src-tauri/tauri.windows.conf.json
fi
test -s "$CAND"
cp "$CAND" "$STAGE/$WINDOWS_GENERIC_ASSET"
cp "$CAND" "$STAGE/$WINDOWS_VERSIONED_ASSET"
python3 - "$STAGE/$WINDOWS_GENERIC_ASSET" <<'PY'
import sys
from pathlib import Path
p=Path(sys.argv[1])
assert p.stat().st_size>1_000_000,p.stat().st_size
assert p.read_bytes()[:2]==b'MZ'
print('ENDLUME_1003_WINDOWS_PE_GREEN',p.stat().st_size)
PY

export TAURI_SIGNING_PRIVATE_KEY_PATH="$HOME/.endlume-updater/endlume.key"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD=""
unset TAURI_SIGNING_PRIVATE_KEY || true
npx --yes @tauri-apps/cli@2.10.1 signer sign "$STAGE/$WINDOWS_GENERIC_ASSET"
cp "$STAGE/$WINDOWS_GENERIC_ASSET.sig" "$STAGE/$WINDOWS_VERSIONED_ASSET.sig"
test -s "$STAGE/$WINDOWS_GENERIC_ASSET.sig"
echo ENDLUME_1003_WINDOWS_SIGNED_GREEN

WIN_SIG="$(tr -d '\r\n' < "$STAGE/$WINDOWS_GENERIC_ASSET.sig")"
WIN_SHA="$(shasum -a 256 "$STAGE/$WINDOWS_GENERIC_ASSET" | awk '{print $1}')"
export STABLE_REPO STABLE_TAG WINDOWS_GENERIC_ASSET
python3 - "$STAGE/latest-mac.json" "$STAGE/latest.json" "$WIN_SIG" "$WIN_SHA" <<'PY'
import datetime,json,os,sys
src,out,sig,sha=sys.argv[1:]
d=json.load(open(src))
assert d.get('version')=='10.0.3'
assert 'darwin-aarch64' in d.get('platforms',{})
base=f"https://github.com/{os.environ['STABLE_REPO']}/releases/download/{os.environ['STABLE_TAG']}"
d['notes']='ENDLUME 10.0.3: accelerated physical masters and AAC caching, bounded build/runtime caches, SSD and TOSHIBA performance gates. Stable for macOS ARM64 and Windows x64.'
d['pub_date']=datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')
d['platforms']['windows-x86_64']={'url':f"{base}/{os.environ['WINDOWS_GENERIC_ASSET']}",'signature':sig,'sha256':sha}
json.dump(d,open(out,'w'),ensure_ascii=False,indent=2)
print('ENDLUME_1003_DUAL_MANIFEST_GREEN')
PY

gh release upload "$STABLE_TAG"   "$STAGE/$WINDOWS_GENERIC_ASSET"   "$STAGE/$WINDOWS_GENERIC_ASSET.sig"   "$STAGE/$WINDOWS_VERSIONED_ASSET"   "$STAGE/$WINDOWS_VERSIONED_ASSET.sig"   --clobber --repo "$STABLE_REPO"
gh release upload "$STABLE_TAG" "$STAGE/latest.json" --clobber --repo "$STABLE_REPO"

gh api "repos/$STABLE_REPO/releases/tags/$STABLE_TAG" > "$STAGE/release-final.json"
LATEST_FINAL_ID="$(python3 - "$STAGE/release-final.json" <<'PY'
import json,os,sys
r=json.load(open(sys.argv[1]));m={a['name']:a for a in r.get('assets',[])}
for n in [os.environ['WINDOWS_GENERIC_ASSET'],os.environ['WINDOWS_GENERIC_ASSET']+'.sig','latest.json']:
    assert n in m,n
print(m['latest.json']['id'])
PY
)"
gh api -H 'Accept: application/octet-stream' "repos/$STABLE_REPO/releases/assets/$LATEST_FINAL_ID" > "$STAGE/latest-public.json"
python3 - "$STAGE/latest-public.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
assert d.get('version')=='10.0.3',d
assert {'darwin-aarch64','windows-x86_64'} <= set(d.get('platforms',{})),d
for k in ('darwin-aarch64','windows-x86_64'):
    p=d['platforms'][k]
    assert p.get('url') and p.get('signature') and p.get('sha256'),d
    assert len(p['sha256'])==64,d
print('ENDLUME_1003_DUAL_STABLE_PUBLIC_GREEN', {k:d['platforms'][k]['sha256'] for k in ('darwin-aarch64','windows-x86_64')})
PY
