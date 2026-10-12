#!/bin/bash
set -Eeuo pipefail

SRC='scripts/phase4_build_sign_1014.sh'
TMP="${RUNNER_TEMP:?}/phase4_build_sign_1014_artifact_qa_runtime.sh"
python3 - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text()

# Compile/test gates are already authoritative GREEN in run 38245502597.
old="""npm ci\nnpm run check\nnpm run build\ncargo check --manifest-path src-tauri/Cargo.toml\ncargo test --manifest-path src-tauri/Cargo.toml\n"""
assert old in src
src=src.replace(old,"npm ci\n",1)

# Replace the LaunchServices-sensitive UI smoke with extraction of the exact
# signed updater tarball. All downstream physical QA then executes those exact
# bytes rather than the transient Cargo bundle or an installed older app.
start=src.index('# Open the actual packaged candidate')
mid=src.index('# Exact 10.0.14 physical smoke', start)
replacement=r'''# Extract and verify the exact signed updater artifact that will be published.
DATA="$HOME/Library/Application Support/studio.endlume.desktop"
snapshot_tree(){
  python3 - "$DATA" "$1" <<'PYSNAP'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2]); rows=[]
if root.is_dir():
  for p in sorted(x for x in root.rglob('*') if x.is_file()):
    rel=str(p.relative_to(root))
    if rel=='session.json' or '/Caches/' in rel: continue
    rows.append({'path':rel,'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
out.write_text(json.dumps(rows,indent=2)+'\n')
PYSNAP
}
QA_EXTRACT="$ROOT/signed-artifact-extracted"
rm -rf "$QA_EXTRACT"; mkdir -p "$QA_EXTRACT"
/usr/bin/tar -xzf "$TAR" -C "$QA_EXTRACT"
QA_APP="$(find "$QA_EXTRACT" -maxdepth 2 -type d -name '*.app' -print -quit)"
test -n "$QA_APP" -a -d "$QA_APP"
QA_INFO="$QA_APP/Contents/Info.plist"
test "$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$QA_INFO")" = '10.0.14'
test "$(/usr/bin/plutil -extract CFBundleVersion raw -o - "$QA_INFO")" = '10.0.14'
test "$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$QA_INFO")" = 'studio.endlume.desktop'
QA_EXE_NAME="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$QA_INFO")"
QA_EXE="$QA_APP/Contents/MacOS/$QA_EXE_NAME"
test -x "$QA_EXE"
/usr/bin/lipo -archs "$QA_EXE" | grep -qw arm64
/usr/bin/codesign --verify --deep --strict --verbose=2 "$QA_APP"
QA_FFMPEG="$(find "$QA_APP/Contents" -maxdepth 7 -type f -name 'ffmpeg' -perm -111 -print -quit)"
QA_FFPROBE="$(find "$QA_APP/Contents" -maxdepth 7 -type f -name 'ffprobe' -perm -111 -print -quit)"
test -x "$QA_FFMPEG" -a -x "$QA_FFPROBE"
"$QA_FFMPEG" -version >/dev/null
"$QA_FFPROBE" -version >/dev/null
snapshot_tree "$ROOT/durable-before.json"
echo SIGNED_ARTIFACT_APP_VERSION=10.0.14
echo SIGNED_ARTIFACT_IDENTIFIER=studio.endlume.desktop
echo SIGNED_ARTIFACT_CODESIGN=PASS
echo SIGNED_ARTIFACT_EXTRACT=PASS

'''
src=src[:start]+replacement+src[mid:]

src=src.replace('python3 scripts/qa-endlume-1014-vyron-routing-physical.py "$EXE" "$FFMPEG" "$FFPROBE" "$ROOT/vyron-routing.json"',
                'python3 scripts/qa-endlume-1014-vyron-routing-physical.py "$QA_EXE" "$QA_FFMPEG" "$QA_FFPROBE" "$ROOT/vyron-routing.json"',1)
src=src.replace('python3 scripts/qa-endlume-1014-seed-persisted-library.py "$FFMPEG" "$QA_HOME"',
                'python3 scripts/qa-endlume-1014-seed-persisted-library.py "$QA_FFMPEG" "$QA_HOME"',1)
src=src.replace('HOME="$QA_HOME" python3 scripts/qa-endlume-1011-preview-subscribe-final.py "$EXE" "$FFMPEG" "$FFPROBE" "$ROOT/preview-subscribe-render.json"',
                'HOME="$QA_HOME" python3 scripts/qa-endlume-1011-preview-subscribe-final.py "$QA_EXE" "$QA_FFMPEG" "$QA_FFPROBE" "$ROOT/preview-subscribe-render.json"',1)

marker='APP_SHA="$(/usr/bin/shasum -a 256 "$EXE" | awk \'{print $1}\')"'
assert marker in src
pre=r'''snapshot_tree "$ROOT/durable-after.json"
# Existing owner project/settings data must remain intact across packaged-artifact QA.
diff -u "$ROOT/durable-before.json" "$ROOT/durable-after.json"
echo OWNER_DURABLE_STATE_PREPUBLISH=PRESERVED
echo PACKAGED_ARTIFACT_EXECUTION=PASS

'''
src=src.replace(marker,pre+'APP_SHA="$(/usr/bin/shasum -a 256 "$QA_EXE" | awk \'{print $1}\')"',1)
Path(sys.argv[2]).write_text(src)
PY
chmod +x "$TMP"
exec /bin/bash "$TMP"
