#!/bin/bash
set -Eeuo pipefail

BASE='55372b94a35ef76ee160347783cf8c62e003fa4e'
VERSION='10.0.14'
export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.cargo/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

[ "${RUNNER_NAME:-}" = 'kirill-mac-endlume' ]
[ "$(uname -s)" = Darwin ]
[ "$(uname -m)" = arm64 ]
git cat-file -e "$BASE^{commit}"
git merge-base --is-ancestor "$BASE" HEAD
git diff --quiet "$BASE" HEAD -- src src-tauri/src
git diff --quiet "$BASE" HEAD -- src-tauri/icons

echo FUNCTIONAL_SOURCE_HEAD="$BASE"
echo FUNCTIONAL_PRODUCT_DIFF=0

python3 - <<'PY'
import json,re,subprocess
from pathlib import Path
v='10.0.14'
assert json.loads(Path('package.json').read_text())['version']==v
lock=json.loads(Path('package-lock.json').read_text())
assert lock['version']==v and lock['packages']['']['version']==v
assert json.loads(Path('src-tauri/tauri.conf.json').read_text())['version']==v
assert re.search(r'\[package\][\s\S]*?\nversion\s*=\s*"10\.0\.14"',Path('src-tauri/Cargo.toml').read_text())
assert re.search(r'\[\[package\]\]\nname = "endlume"\nversion = "10\.0\.14"',Path('src-tauri/Cargo.lock').read_text())
cur=json.loads(Path('src-tauri/tauri.conf.json').read_text())
old=json.loads(subprocess.check_output(['git','show','55372b94a35ef76ee160347783cf8c62e003fa4e:src-tauri/tauri.conf.json'],text=True))
assert cur['identifier']==old['identifier']=='studio.endlume.desktop'
assert cur['plugins']['updater']['pubkey']==old['plugins']['updater']['pubkey']
assert cur['plugins']['updater']['endpoints']==old['plugins']['updater']['endpoints']==['https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/latest.json']
print('VERSION_SURFACES=10.0.14')
print('APP_IDENTIFIER=UNCHANGED')
print('UPDATER_PUBKEY=UNCHANGED')
print('UPDATER_ENDPOINT=UNCHANGED')
PY

KEY="$HOME/.endlume-updater/endlume.key"
PUB="$HOME/.endlume-updater/endlume.key.pub"
test -s "$KEY" -a -s "$PUB"
python3 - "$PUB" <<'PY'
import json,sys
from pathlib import Path
cfg=json.loads(Path('src-tauri/tauri.conf.json').read_text())
embedded=cfg['plugins']['updater']['pubkey'].strip()
disk=Path(sys.argv[1]).read_text().replace('\r','').replace('\n','').strip()
assert embedded==disk,(len(embedded),len(disk))
print('UPDATER_TRUST_ROOT=PASS')
print('KEY_ROTATION=NO')
PY

FOUNDATION="$HOME/.endlume-local-builder/endlume-desktop-8.40-bootstrap"
test -d "$FOUNDATION/src-tauri/binaries"
mkdir -p src-tauri/binaries
rsync -a "$FOUNDATION/src-tauri/binaries/" src-tauri/binaries/

export CARGO_TARGET_DIR="$RUNNER_TEMP/../_endlume-cache/target-1014-stable"
npm ci
npm run check
npm run build
cargo check --manifest-path src-tauri/Cargo.toml
cargo test --manifest-path src-tauri/Cargo.toml

ROOT="$RUNNER_TEMP/endlume-1014-release"
STAGE="$RUNNER_TEMP/endlume-1014-signed-stage"
rm -rf "$ROOT" "$STAGE"
mkdir -p "$ROOT" "$STAGE"
CONF='src-tauri/tauri.conf.json'
CONF_BACKUP="$ROOT/tauri.conf.original.json"
cp "$CONF" "$CONF_BACKUP"
restore_conf(){ cp "$CONF_BACKUP" "$CONF"; }
trap restore_conf EXIT
python3 - <<'PY'
import json
from pathlib import Path
p=Path('src-tauri/tauri.conf.json')
d=json.loads(p.read_text())
d['bundle']['createUpdaterArtifacts']=False
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
PY
ENDLUME_TAURI_TARGET=aarch64-apple-darwin node scripts/prepare-macos-ffmpeg-runtime.mjs
npx tauri build --target aarch64-apple-darwin --bundles app --features e2e-render
restore_conf
trap - EXIT

git diff --quiet "$BASE" HEAD -- src src-tauri/src
APP="$(find "$CARGO_TARGET_DIR/aarch64-apple-darwin/release/bundle/macos" -maxdepth 1 -type d -name '*.app' -print -quit)"
test -n "$APP" -a -d "$APP"
INFO="$APP/Contents/Info.plist"
test "$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$INFO")" = "$VERSION"
test "$(/usr/bin/plutil -extract CFBundleVersion raw -o - "$INFO")" = "$VERSION"
test "$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$INFO")" = 'studio.endlume.desktop'
EXE_NAME="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$INFO")"
EXE="$APP/Contents/MacOS/$EXE_NAME"
/usr/bin/lipo -archs "$EXE" | grep -qw arm64
/usr/bin/codesign --force --deep --sign - --timestamp=none "$APP"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP"
FFMPEG="$(find "$APP/Contents" -maxdepth 7 -type f -name 'ffmpeg' -perm -111 -print -quit)"
FFPROBE="$(find "$APP/Contents" -maxdepth 7 -type f -name 'ffprobe' -perm -111 -print -quit)"
test -x "$FFMPEG" -a -x "$FFPROBE"
"$FFMPEG" -version >/dev/null
"$FFPROBE" -version >/dev/null

echo PACKAGED_APP_VERSION=10.0.14
echo PACKAGED_APP_IDENTIFIER=studio.endlume.desktop
echo CODESIGN_VERIFY=PASS

ZIP="$STAGE/ENDLUME-10.0.14-macos-aarch64.app.zip"
TAR="$STAGE/ENDLUME-10.0.14-macos-aarch64.app.tar.gz"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
/usr/bin/tar -czf "$TAR" -C "$(dirname "$APP")" "$(basename "$APP")"
export TAURI_SIGNING_PRIVATE_KEY_PATH="$KEY"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD=''
unset TAURI_SIGNING_PRIVATE_KEY || true
npx --yes @tauri-apps/cli@2.10.1 signer sign "$TAR"
test -s "$TAR.sig"

command -v minisign >/dev/null 2>&1 || /opt/homebrew/bin/brew install minisign
python3 - "$PUB" "$TAR.sig" "$ROOT/minisign.pub" "$ROOT/minisign.sig" <<'PY'
import base64,sys
from pathlib import Path
Path(sys.argv[3]).write_bytes(base64.b64decode(Path(sys.argv[1]).read_text().strip()))
Path(sys.argv[4]).write_bytes(base64.b64decode(Path(sys.argv[2]).read_text().strip()))
PY
minisign -Vm "$TAR" -p "$ROOT/minisign.pub" -x "$ROOT/minisign.sig"
echo UPDATER_SIGNATURE_VERIFY=PASS

# Open the actual packaged candidate with the owner's normal profile and prove durable data is not reset.
DATA="$HOME/Library/Application Support/studio.endlume.desktop"
snapshot_tree(){
  python3 - "$DATA" "$1" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2]); rows=[]
if root.is_dir():
  for p in sorted(x for x in root.rglob('*') if x.is_file()):
    rel=str(p.relative_to(root))
    if rel=='session.json' or '/Caches/' in rel: continue
    rows.append({'path':rel,'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
out.write_text(json.dumps(rows,indent=2)+'\n')
PY
}
snapshot_tree "$ROOT/durable-before.json"
open -n "$APP"
CANDIDATE_PID=''
for i in $(seq 1 45); do
  for p in $(pgrep -x "$EXE_NAME" 2>/dev/null || true); do
    cmd="$(ps -p "$p" -o command= 2>/dev/null || true)"
    case "$cmd" in "$APP/Contents/MacOS/$EXE_NAME"*) CANDIDATE_PID="$p"; break 2;; esac
  done
  sleep 1
done
test -n "$CANDIDATE_PID"
sleep 4
kill -0 "$CANDIDATE_PID"
kill "$CANDIDATE_PID" 2>/dev/null || true
sleep 2
snapshot_tree "$ROOT/durable-after.json"
diff -u "$ROOT/durable-before.json" "$ROOT/durable-after.json"
echo PACKAGED_UI_LAUNCH=PASS
echo OWNER_DURABLE_STATE_PREPUBLISH=PRESERVED

# Exact 10.0.14 physical smoke on the newly packaged binary.
test -d '/Volumes/TOSHIBA EXT'
python3 scripts/qa-endlume-1014-vyron-routing-physical.py "$EXE" "$FFMPEG" "$FFPROBE" "$ROOT/vyron-routing.json" | tee "$ROOT/vyron-routing.log"
QA_HOME="$RUNNER_TEMP/endlume-1014-release-isolated-home"
rm -rf "$QA_HOME"; mkdir -p "$QA_HOME"
python3 scripts/qa-endlume-1014-seed-persisted-library.py "$FFMPEG" "$QA_HOME" | tee "$ROOT/persisted-library-seed.log"
HOME="$QA_HOME" python3 scripts/qa-endlume-1011-preview-subscribe-final.py "$EXE" "$FFMPEG" "$FFPROBE" "$ROOT/preview-subscribe-render.json" | tee "$ROOT/preview-subscribe-render.log"
python3 - "$ROOT/vyron-routing.json" "$ROOT/preview-subscribe-render.json" <<'PY'
import json,sys
v=json.load(open(sys.argv[1])); q=json.load(open(sys.argv[2]))
assert v['status']=='GREEN' and v['crossWrite'] is False,v
assert q['status']=='GREEN',q
assert q['preview']['effectsBackend']=='GREEN',q
assert q['preview']['effectsFrontend']['status']=='GREEN',q
assert q['preview']['subscribeBackend']=='GREEN',q
assert q['preview']['subscribeFrontend']['status']=='GREEN',q
assert q['subscribeFinal']=='GREEN',q
assert q['roundEqualizer']=='GREEN' and q['otherEffect']=='GREEN',q
print('VYRON_PREPUBLISH=PASS')
print('EFFECTS_PREVIEW_PREPUBLISH=PASS')
print('SUBSCRIBE_PREVIEW_PREPUBLISH=PASS')
print('REAL_RENDER_PREPUBLISH=PASS')
PY

APP_SHA="$(/usr/bin/shasum -a 256 "$EXE" | awk '{print $1}')"
ZIP_SHA="$(/usr/bin/shasum -a 256 "$ZIP" | awk '{print $1}')"
TAR_SHA="$(/usr/bin/shasum -a 256 "$TAR" | awk '{print $1}')"
SIG_SHA="$(/usr/bin/shasum -a 256 "$TAR.sig" | awk '{print $1}')"
SIG="$(tr -d '\r\n' < "$TAR.sig")"
cp "$TAR" "$STAGE/ENDLUME-macos-aarch64.app.tar.gz"
cp "$TAR.sig" "$STAGE/ENDLUME-macos-aarch64.app.tar.gz.sig"
python3 - "$STAGE/ENDLUME-10.0.14-release.json" "${GITHUB_SHA:-UNKNOWN}" "$APP_SHA" "$ZIP_SHA" "$TAR_SHA" "$SIG_SHA" <<'PY'
import json,sys
out,head,app_sha,zip_sha,tar_sha,sig_sha=sys.argv[1:]
d={
 'releaseStatus':'PREPUBLISH_PHYSICAL_PASS','releaseVersion':'10.0.14','releaseHead':head,
 'functionalSourceHead':'55372b94a35ef76ee160347783cf8c62e003fa4e','physicalAcceptanceRun':'38231795588',
 'functionalProductDiff':0,'appIdentifier':'studio.endlume.desktop','updaterEndpoint':'https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/latest.json',
 'appExecutableSha256':app_sha,'appZipSha256':zip_sha,'tarGzSha256':tar_sha,'signatureSha256':sig_sha,
 'signatureVerify':'PASS','packagedSmoke':'PASS','vyron':'PASS','effectsPreview':'PASS','subscribePreview':'PASS','realRender':'PASS',
 'mediaContract':'HEVC_1920x1080_60_AAC_48K_STEREO_400_600_MIB','ownerAuthorization':'RELEASE 10.0.14 APPROVED'
}
json.dump(d,open(out,'w'),ensure_ascii=False,indent=2)
PY
/usr/bin/shasum -a 256 "$STAGE"/ENDLUME-10.0.14-* "$STAGE/ENDLUME-macos-aarch64.app.tar.gz" "$STAGE/ENDLUME-macos-aarch64.app.tar.gz.sig" > "$STAGE/SHA256SUMS.txt"
cp "$ROOT/vyron-routing.json" "$STAGE/"
cp "$ROOT/preview-subscribe-render.json" "$STAGE/"
cp "$ROOT/durable-before.json" "$STAGE/"
cp "$ROOT/durable-after.json" "$STAGE/"

echo "PHASE4_STAGE=$STAGE" >> "$GITHUB_ENV"
echo APP_SHA256="$APP_SHA"
echo APP_ZIP_SHA256="$ZIP_SHA"
echo TAR_GZ_SHA256="$TAR_SHA"
echo SIGNATURE_SHA256="$SIG_SHA"
echo UPDATER_SIGNATURE_BASE64="$SIG"
echo ENDLUME_1014_PREPUBLISH_PHYSICAL=PASS
