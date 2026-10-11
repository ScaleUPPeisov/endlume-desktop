#!/bin/bash
set -Eeuo pipefail

BASE=e4a07972b1566ed73b11c4eb758d59f4dc839e71
VERSION=10.0.13
OWNER_SHA=2df386c00da09e76f90218061e7f57ccfba2249a654ec1262b06000b322eb9d7
PUB_SHA=c320c0fbea2d494349f780cee70267d97eab9d4a0bde5e8721a0c9acb18548d6
export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.cargo/bin:$PATH"

[ "${RUNNER_NAME:-}" = kirill-mac-endlume ]
[ "$(uname -s)" = Darwin ]
[ "$(uname -m)" = arm64 ]
git cat-file -e "$BASE^{commit}"
git merge-base --is-ancestor "$BASE" HEAD
BAD="$(git diff --name-only "$BASE" HEAD | grep -Ev '^(package\.json|package-lock\.json|src-tauri/Cargo\.toml|src-tauri/Cargo\.lock|src-tauri/tauri\.conf\.json|src/components/ReleaseHistory\.tsx|RELEASE_NOTES\.md|release/ENDLUME_10\.0\.13_RELEASE\.md|scripts/phase4_(prepare_1013\.py|build_sign_1013\.sh)|\.github/workflows/endlume-1013-phase4-(prepare|build-sign)\.yml)$' || true)"
[ -z "$BAD" ] || { printf '%s\n' "$BAD" >&2; exit 21; }
git diff --quiet "$BASE" HEAD -- src-tauri/src
git diff --quiet "$BASE" HEAD -- src-tauri/icons
BAD_SRC="$(git diff --name-only "$BASE" HEAD -- src | grep -Ev '^src/components/ReleaseHistory\.tsx$' || true)"
[ -z "$BAD_SRC" ]

python3 - <<'PY'
import json,re
from pathlib import Path
v='10.0.13'
assert json.loads(Path('package.json').read_text())['version']==v
lock=json.loads(Path('package-lock.json').read_text())
assert lock['version']==v and lock['packages']['']['version']==v
assert json.loads(Path('src-tauri/tauri.conf.json').read_text())['version']==v
assert re.search(r'\[package\][\s\S]*?\nversion\s*=\s*"10\.0\.13"',Path('src-tauri/Cargo.toml').read_text())
assert re.search(r'\[\[package\]\]\nname = "endlume"\nversion = "10\.0\.13"',Path('src-tauri/Cargo.lock').read_text())
h=Path('src/components/ReleaseHistory.tsx').read_text()
assert "version:'10.0.13',date:'11.10.2026',current:true" in h
assert h.count('current:true')==1
PY

echo FAST_ENGINE_FUNCTIONAL_DIFF=0
echo PROJECT_UI_FUNCTIONAL_DIFF=0
echo EFFECTS_FUNCTIONAL_DIFF=0
echo SUBSCRIBE_FUNCTIONAL_DIFF=0
echo PREVIEW_FUNCTIONAL_DIFF=0
echo RENDER_CENTER_FUNCTIONAL_DIFF=0
echo ICON_DIFF=0

KEY="$HOME/.endlume-updater/endlume.key"
PUB="$HOME/.endlume-updater/endlume.key.pub"
[ -s "$KEY" ] && [ -s "$PUB" ]
python3 - "$PUB" <<'PY'
import base64,hashlib,json,sys
from pathlib import Path
cfg=json.loads(Path('src-tauri/tauri.conf.json').read_text())
embedded=cfg['plugins']['updater']['pubkey'].strip()
disk=Path(sys.argv[1]).read_text().replace('\r','').replace('\n','').strip()
assert embedded==disk
assert hashlib.sha256(embedded.encode()).hexdigest()=='c320c0fbea2d494349f780cee70267d97eab9d4a0bde5e8721a0c9acb18548d6'
lines=[x.strip() for x in base64.b64decode(embedded).decode().splitlines() if x.strip()]
assert 'D322CD50491D3500' in lines[0]
assert base64.b64decode(lines[1])[2:10].hex()=='00351d4950cd22d3'
PY
echo UPDATER_TRUST_ROOT=PASS
echo KEY_ROTATION=NO

OWNER='/Applications/ENDLUME YT Studio PEISOV.app'
[ -d "$OWNER" ]
[ "$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$OWNER/Contents/Info.plist")" = 10.0.12 ]
[ "$(/usr/bin/plutil -extract CFBundleVersion raw -o - "$OWNER/Contents/Info.plist")" = 10.0.12 ]
OWNER_EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$OWNER/Contents/Info.plist")"
ACTUAL_OWNER_SHA="$(/usr/bin/shasum -a 256 "$OWNER/Contents/MacOS/$OWNER_EXE" | awk '{print $1}')"
[ "$ACTUAL_OWNER_SHA" = "$OWNER_SHA" ]
echo OWNER_PREUPDATE_VERSION=10.0.12
echo OWNER_PREUPDATE_BINARY_SHA256="$ACTUAL_OWNER_SHA"

TMP="$(mktemp -d)"
mkdir -p "$TMP/fm" "$TMP/fp" src-tauri/binaries
curl -fL --retry 4 'https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip' -o "$TMP/ffmpeg.zip"
curl -fL --retry 4 'https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffprobe.zip' -o "$TMP/ffprobe.zip"
/usr/bin/ditto -x -k "$TMP/ffmpeg.zip" "$TMP/fm"
/usr/bin/ditto -x -k "$TMP/ffprobe.zip" "$TMP/fp"
FFMPEG="$(find "$TMP/fm" -type f -name ffmpeg -print -quit)"
FFPROBE="$(find "$TMP/fp" -type f -name ffprobe -print -quit)"
[ -n "$FFMPEG" ] && [ -n "$FFPROBE" ]
cp "$FFMPEG" src-tauri/binaries/ffmpeg-aarch64-apple-darwin
cp "$FFPROBE" src-tauri/binaries/ffprobe-aarch64-apple-darwin
chmod 755 src-tauri/binaries/ffmpeg-aarch64-apple-darwin src-tauri/binaries/ffprobe-aarch64-apple-darwin

export CARGO_TARGET_DIR="$RUNNER_TEMP/endlume-1013-phase4-target"
npm ci
npm run check
npm run build
ENDLUME_TAURI_TARGET=aarch64-apple-darwin node scripts/prepare-macos-ffmpeg-runtime.mjs
python3 - <<'PY'
import json
from pathlib import Path
p=Path('src-tauri/tauri.conf.json'); d=json.loads(p.read_text()); d['bundle']['createUpdaterArtifacts']=False; p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
PY
npx tauri build --target aarch64-apple-darwin --bundles app --features e2e-render
APP="$(find "$CARGO_TARGET_DIR/aarch64-apple-darwin/release/bundle/macos" -maxdepth 1 -type d -name '*.app' -print -quit)"
[ -n "$APP" ] && [ -d "$APP" ]
[ "$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$APP/Contents/Info.plist")" = "$VERSION" ]
[ "$(/usr/bin/plutil -extract CFBundleVersion raw -o - "$APP/Contents/Info.plist")" = "$VERSION" ]
EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$APP/Contents/Info.plist")"
/usr/bin/lipo -archs "$APP/Contents/MacOS/$EXE" | grep -qw arm64
/usr/bin/codesign --force --deep --sign - --timestamp=none "$APP"
/usr/bin/codesign --verify --deep --strict "$APP"
"$APP/Contents/MacOS/ffmpeg" -version >/dev/null
"$APP/Contents/MacOS/ffprobe" -version >/dev/null

STAGE="$RUNNER_TEMP/endlume-1013-phase4-stage"
rm -rf "$STAGE"; mkdir -p "$STAGE/unpack"
ZIP="$STAGE/ENDLUME-10.0.13-macos-aarch64.app.zip"
TAR="$STAGE/ENDLUME-10.0.13-macos-aarch64.app.tar.gz"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
/usr/bin/tar -czf "$TAR" -C "$(dirname "$APP")" "$(basename "$APP")"
export TAURI_SIGNING_PRIVATE_KEY_PATH="$KEY"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD=''
unset TAURI_SIGNING_PRIVATE_KEY || true
npx --yes @tauri-apps/cli@2.10.1 signer sign "$TAR"
[ -s "$TAR.sig" ]
command -v minisign >/dev/null 2>&1 || /opt/homebrew/bin/brew install minisign
python3 - "$PUB" "$TAR.sig" "$STAGE/minisign.pub" "$STAGE/minisign.sig" <<'PY'
import base64,sys
from pathlib import Path
Path(sys.argv[3]).write_bytes(base64.b64decode(Path(sys.argv[1]).read_text().strip()))
Path(sys.argv[4]).write_bytes(base64.b64decode(Path(sys.argv[2]).read_text().strip()))
PY
minisign -Vm "$TAR" -p "$STAGE/minisign.pub" -x "$STAGE/minisign.sig"

APP_SHA="$(/usr/bin/shasum -a 256 "$APP/Contents/MacOS/$EXE" | awk '{print $1}')"
ZIP_SHA="$(/usr/bin/shasum -a 256 "$ZIP" | awk '{print $1}')"
TAR_SHA="$(/usr/bin/shasum -a 256 "$TAR" | awk '{print $1}')"
SIG_SHA="$(/usr/bin/shasum -a 256 "$TAR.sig" | awk '{print $1}')"
SIG="$(tr -d '\r\n' < "$TAR.sig")"
cp "$TAR" "$STAGE/ENDLUME-macos-aarch64.app.tar.gz"
cp "$TAR.sig" "$STAGE/ENDLUME-macos-aarch64.app.tar.gz.sig"
python3 - "$STAGE/latest.json" "$SIG" "$TAR_SHA" <<'PY'
import datetime,json,sys
out,sig,sha=sys.argv[1:]
base='https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/'
d={'version':'10.0.13','notes':'ENDLUME 10.0.13 — canonical modern ENDLUME with Fast Engine acceleration. Known Preview-only periodic boundary issue accepted.','pub_date':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z'),'platforms':{'darwin-aarch64':{'url':base+'ENDLUME-macos-aarch64.app.tar.gz','signature':sig,'sha256':sha}}}
json.dump(d,open(out,'w'),ensure_ascii=False,indent=2)
PY
python3 - "$STAGE/ENDLUME-10.0.13-release.json" "${GITHUB_SHA:-UNKNOWN}" "$APP_SHA" "$ZIP_SHA" "$TAR_SHA" "$SIG_SHA" <<'PY'
import json,sys
out,head,app_sha,zip_sha,tar_sha,sig_sha=sys.argv[1:]
d={'releaseStatus':'PREFLIGHT_PASS','releaseVersion':'10.0.13','releaseHead':head,'sourceEngineHead':'e4a07972b1566ed73b11c4eb758d59f4dc839e71','functionalProductDiff':0,'fastEngineFunctionalDiff':0,'projectUiFunctionalDiff':0,'effectsFunctionalDiff':0,'subscribeFunctionalDiff':0,'previewFunctionalDiff':0,'renderCenterFunctionalDiff':0,'iconDiff':0,'appExecutableSha256':app_sha,'appZipSha256':zip_sha,'tarGzSha256':tar_sha,'signatureSha256':sig_sha,'signatureVerify':'PASS','latestJsonSha256Field':'PASS','keyRotation':'NO','updaterKeyId':'00351d4950cd22d3','updaterPubkeySha256':'c320c0fbea2d494349f780cee70267d97eab9d4a0bde5e8721a0c9acb18548d6','knownIssue':'KNOWN_PREVIEW_ONLY_PERIODIC_BOUNDARY_ISSUE'}
json.dump(d,open(out,'w'),indent=2)
PY
/usr/bin/shasum -a 256 "$STAGE"/ENDLUME-10.0.13-* "$STAGE/latest.json" "$STAGE/ENDLUME-macos-aarch64.app.tar.gz" "$STAGE/ENDLUME-macos-aarch64.app.tar.gz.sig" > "$STAGE/SHA256SUMS.txt"

echo "PHASE4_STAGE=$STAGE" >> "$GITHUB_ENV"
echo APP_SHA256="$APP_SHA"
echo APP_ZIP_SHA256="$ZIP_SHA"
echo TAR_GZ_SHA256="$TAR_SHA"
echo SIGNATURE_SHA256="$SIG_SHA"
echo UPDATER_SIGNATURE_BASE64="$SIG"
echo CODESIGN_VERIFY=PASS
echo UPDATER_SIGNATURE_VERIFY=PASS
echo LATEST_JSON_SHA256_FIELD=PASS
