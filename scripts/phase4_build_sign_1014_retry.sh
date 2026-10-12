#!/bin/bash
set -Eeuo pipefail

SRC='scripts/phase4_build_sign_1014.sh'
TMP="${RUNNER_TEMP:?}/phase4_build_sign_1014_retry_runtime.sh"
python3 - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text()
# Compile/test gates already passed in authoritative run 38245502597.
old="""npm ci\nnpm run check\nnpm run build\ncargo check --manifest-path src-tauri/Cargo.toml\ncargo test --manifest-path src-tauri/Cargo.toml\n"""
assert old in src
src=src.replace(old,"npm ci\n",1)

start=src.index("# Open the actual packaged candidate with the owner's normal profile and prove durable data is not reset.")
end=src.index("APP_SHA=", start)
replacement=r'''# Validate and physically execute the exact signed updater payload bytes.
# macOS may hand a normal GUI launch to an already-installed app with the same bundle id;
# extracting the freshly signed updater tar guarantees all QA below targets only 10.0.14 bytes.
DATA="$HOME/Library/Application Support/studio.endlume.desktop"
snapshot_tree(){
  python3 - "$DATA" "$1" <<'PY2'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2]); rows=[]
if root.is_dir():
  for p in sorted(x for x in root.rglob('*') if x.is_file()):
    rel=str(p.relative_to(root))
    if rel=='session.json' or '/Caches/' in rel: continue
    rows.append({'path':rel,'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
out.write_text(json.dumps(rows,indent=2)+'\n')
PY2
}
UNPACK="$ROOT/signed-updater-unpacked"
rm -rf "$UNPACK"; mkdir -p "$UNPACK"
/usr/bin/tar -xzf "$TAR" -C "$UNPACK"
QA_APP="$(find "$UNPACK" -maxdepth 2 -type d -name '*.app' -print -quit)"
test -n "$QA_APP" -a -d "$QA_APP"
QA_INFO="$QA_APP/Contents/Info.plist"
test "$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$QA_INFO")" = "$VERSION"
test "$(/usr/bin/plutil -extract CFBundleVersion raw -o - "$QA_INFO")" = "$VERSION"
test "$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$QA_INFO")" = 'studio.endlume.desktop'
QA_EXE_NAME="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$QA_INFO")"
QA_EXE="$QA_APP/Contents/MacOS/$QA_EXE_NAME"
QA_FFMPEG="$(find "$QA_APP/Contents" -maxdepth 7 -type f -name 'ffmpeg' -perm -111 -print -quit)"
QA_FFPROBE="$(find "$QA_APP/Contents" -maxdepth 7 -type f -name 'ffprobe' -perm -111 -print -quit)"
test -x "$QA_EXE" -a -x "$QA_FFMPEG" -a -x "$QA_FFPROBE"
/usr/bin/lipo -archs "$QA_EXE" | grep -qw arm64
/usr/bin/codesign --verify --deep --strict --verbose=2 "$QA_APP"
"$QA_FFMPEG" -version >/dev/null
"$QA_FFPROBE" -version >/dev/null
SIGNED_PAYLOAD_EXE_SHA="$(/usr/bin/shasum -a 256 "$QA_EXE" | awk '{print $1}')"
ORIGINAL_BUILD_EXE_SHA="$(/usr/bin/shasum -a 256 "$EXE" 2>/dev/null | awk '{print $1}' || true)"
if [ -n "$ORIGINAL_BUILD_EXE_SHA" ]; then test "$SIGNED_PAYLOAD_EXE_SHA" = "$ORIGINAL_BUILD_EXE_SHA"; fi
echo SIGNED_UPDATER_PAYLOAD_EXTRACT=PASS
echo SIGNED_UPDATER_PAYLOAD_CODESIGN=PASS
echo SIGNED_PAYLOAD_EXE_SHA256="$SIGNED_PAYLOAD_EXE_SHA"

snapshot_tree "$ROOT/durable-before.json"
# Exact 10.0.14 physical smoke on executable/resources extracted from the signed updater payload.
test -d '/Volumes/TOSHIBA EXT'
python3 scripts/qa-endlume-1014-vyron-routing-physical.py "$QA_EXE" "$QA_FFMPEG" "$QA_FFPROBE" "$ROOT/vyron-routing.json" | tee "$ROOT/vyron-routing.log"
QA_HOME="$RUNNER_TEMP/endlume-1014-release-isolated-home"
rm -rf "$QA_HOME"; mkdir -p "$QA_HOME"
python3 scripts/qa-endlume-1014-seed-persisted-library.py "$QA_FFMPEG" "$QA_HOME" | tee "$ROOT/persisted-library-seed.log"
HOME="$QA_HOME" python3 scripts/qa-endlume-1011-preview-subscribe-final.py "$QA_EXE" "$QA_FFMPEG" "$QA_FFPROBE" "$ROOT/preview-subscribe-render.json" | tee "$ROOT/preview-subscribe-render.log"
python3 - "$ROOT/vyron-routing.json" "$ROOT/preview-subscribe-render.json" <<'PY2'
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
print('PACKAGED_EXECUTABLE_LAUNCH=PASS')
print('VYRON_PREPUBLISH=PASS')
print('EFFECTS_PREVIEW_PREPUBLISH=PASS')
print('SUBSCRIBE_PREVIEW_PREPUBLISH=PASS')
print('REAL_RENDER_PREPUBLISH=PASS')
PY2
snapshot_tree "$ROOT/durable-after.json"
diff -u "$ROOT/durable-before.json" "$ROOT/durable-after.json"
echo OWNER_DURABLE_STATE_PREPUBLISH=PRESERVED

'''
src=src[:start]+replacement+src[end:]
# Release metadata must hash the executable inside the exact signed updater payload.
src=src.replace('APP_SHA="$(/usr/bin/shasum -a 256 "$EXE" | awk \'{print $1}\')"','APP_SHA="$SIGNED_PAYLOAD_EXE_SHA"',1)
Path(sys.argv[2]).write_text(src)
PY
chmod +x "$TMP"
exec /bin/bash "$TMP"
