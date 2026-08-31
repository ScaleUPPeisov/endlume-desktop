#!/bin/bash
set -Eeuo pipefail
export COPYFILE_DISABLE=1
export COPY_EXTENDED_ATTRIBUTES_DISABLE=1

REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
TMP="$(mktemp -d /tmp/endlume-840-dragdrop.XXXXXX)"
BASE="$TMP/BUILD_ENDLUME_833_LOCAL.command"
REAL="$TMP/BUILD_ENDLUME_840_DRAGDROP_REAL.command"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo; echo "❌ ENDLUME 8.40 DRAG&DROP: $1"; exit 1; }

echo "ENDLUME Studio 1.0.0-alpha.8.40 • CLEAN DRAG&DROP MAC"
echo "Proven 8.38 base • native internet updater • no 8.39 migration chain"
echo
[[ "$(uname -s)" == Darwin && "$(uname -m)" == arm64 ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"

gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/BUILD_ENDLUME_833_LOCAL.command?ref=$BRANCH" > "$BASE" || fail "не удалось получить proven 8.33 builder"
[[ -s "$BASE" ]] || fail "8.33 builder пуст"
/bin/bash -n "$BASE" || fail "8.33 builder syntax failed"

python3 - "$BASE" "$REAL" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')

src=src.replace('VERSION_EXPECTED="1.0.0-alpha.8.33"','VERSION_EXPECTED="1.0.0-alpha.8.40"',1)
src=src.replace('echo "❌ ENDLUME 8.33 остановлена ДО замены приложения"','echo "❌ ENDLUME 8.40 bootstrap остановлен"',1)
src=src.replace('SRC="$WORK_ROOT/endlume-desktop-8.33"','SRC="$WORK_ROOT/endlume-desktop-8.40-bootstrap"',1)
src=src.replace('│ 8.33 • SSD workdir • Fast Fidelity • Preview repair       │','│ 8.40 • STABLE 8.38 BASE • NATIVE INTERNET UPDATER        │',1)
src=src.replace('WORK_ROOT="$(choose_work_root)"','WORK_ROOT="$HOME/.endlume-local-builder"',1)

# Keep build metadata clean before Tauri parses capabilities/config.
marker='# Prefer the writable external volume with the most free space.'
shield='''sanitize_build_appledouble(){
  [[ -d "${SRC:-}" ]] || return 0
  /usr/bin/find "$SRC" \\
    \\( -path "$SRC/.git" -o -path "$SRC/node_modules" -o -path "$SRC/src-tauri/target" \\) -prune -o \\
    -type f -name '._*' -exec /bin/rm -f {} + 2>/dev/null || true
}
assert_no_tauri_appledouble(){
  sanitize_build_appledouble
  local bad=""
  [[ -d "$SRC/src-tauri/capabilities" ]] && bad="$(/usr/bin/find "$SRC/src-tauri/capabilities" -type f -name '._*' -print -quit 2>/dev/null || true)"
  [[ -z "$bad" ]] || fail "AppleDouble sidecar остался: $bad"
}

'''
if marker in src and 'sanitize_build_appledouble' not in src:
    src=src.replace(marker,shield+marker,1)
clone='gh repo clone "$REPO" "$SRC" -- --branch "$BRANCH" --single-branch\ncd "$SRC"\n'
if clone in src:
    src=src.replace(clone,clone+'sanitize_build_appledouble\n',1)
src=src.replace('npm install --no-audit --no-fund\n','npm install --no-audit --no-fund\nsanitize_build_appledouble\n',1)

# Normalize the proven 8.33 migration first.
speed='python3 scripts/apply-speed-fidelity-8-33.py\n'
if speed in src:
    src=src.replace(speed,'python3 -m py_compile scripts/repair-speed-workdir-8-33.py\npython3 scripts/repair-speed-workdir-8-33.py\n'+speed,1)

# IMPORTANT: stop at proven 8.38. Do NOT apply any 8.39 code in this bootstrap.
marker='python3 scripts/apply-version-8-33.py\n'
addition='''python3 -m py_compile scripts/apply-stability-8-34.py scripts/apply-version-8-34.py scripts/apply-strict-fidelity-8-35.py scripts/apply-version-8-35.py scripts/repair-strict-store-8-35.py scripts/apply-fidelity-1080p-8-36.py scripts/apply-version-8-36.py scripts/repair-settings-updater-8-37.py scripts/apply-remote-updater-8-37.py scripts/apply-version-8-37.py scripts/apply-youtube-fill-8-38.py scripts/apply-version-8-38.py scripts/apply-github-updater-8-40.py scripts/apply-version-8-40.py
python3 scripts/apply-stability-8-34.py
python3 scripts/apply-version-8-34.py
python3 scripts/apply-strict-fidelity-8-35.py
python3 scripts/apply-version-8-35.py
python3 scripts/repair-strict-store-8-35.py
chmod +x scripts/validate-release-8-33.sh scripts/validate-release-8-34.sh
scripts/validate-release-8-33.sh "$FFMPEG" "$FFPROBE"
scripts/validate-release-8-34.sh "$FFMPEG" "$FFPROBE"
python3 scripts/apply-fidelity-1080p-8-36.py
python3 scripts/apply-version-8-36.py
chmod +x scripts/validate-release-8-36.sh
scripts/validate-release-8-36.sh "$FFMPEG" "$FFPROBE"
python3 scripts/repair-settings-updater-8-37.py
python3 scripts/apply-remote-updater-8-37.py
python3 scripts/apply-version-8-37.py
chmod +x scripts/validate-release-8-37.sh
scripts/validate-release-8-37.sh
python3 scripts/apply-youtube-fill-8-38.py
python3 scripts/apply-version-8-38.py
chmod +x scripts/validate-release-8-38.sh
scripts/validate-release-8-38.sh "$FFMPEG" "$FFPROBE"
python3 scripts/apply-github-updater-8-40.py
python3 scripts/apply-version-8-40.py
chmod +x scripts/validate-release-8-40.sh
scripts/validate-release-8-40.sh
'''
if marker not in src:
    raise SystemExit('8.40 bootstrap: 8.33 version marker missing')
src=src.replace(marker,marker+addition,1)

cargo='stage "6.7/10 Проверяю Rust" 50\ncargo check --manifest-path src-tauri/Cargo.toml --target aarch64-apple-darwin\n'
if cargo in src:
    src=src.replace(cargo,'stage "6.7/10 Проверяю Rust" 50\nassert_no_tauri_appledouble\ncargo check --manifest-path src-tauri/Cargo.toml --target aarch64-apple-darwin\n',1)

old_stage='''stage "7/10 Гоняю Effects / Subscribe / Audio / SSD / Fast Fidelity regression" 58
chmod +x scripts/validate-release-8-33.sh
scripts/validate-release-8-33.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs
'''
new_stage='''stage "7/10 Проверяю proven 8.38 + Native Updater" 58
chmod +x scripts/validate-release-8-38.sh scripts/validate-release-8-40.sh
scripts/validate-release-8-38.sh "$FFMPEG" "$FFPROBE"
scripts/validate-release-8-40.sh
node scripts/validate-motion-ui.mjs
'''
if old_stage not in src:
    raise SystemExit('8.40 bootstrap: stage7 marker missing')
src=src.replace(old_stage,new_stage,1)

build='stage "9/10 Собираю ENDLUME Studio.app" 80\nnpx tauri build --target aarch64-apple-darwin --bundles app --config src-tauri/tauri.local.conf.json\n'
if build in src:
    src=src.replace(build,'stage "9/10 Собираю ENDLUME Studio.app" 80\nassert_no_tauri_appledouble\nnpx tauri build --target aarch64-apple-darwin --bundles app --config src-tauri/tauri.local.conf.json\n',1)

# Replace the old /Applications installation stage with one drag-and-drop ZIP.
stage10='stage "10/10 Устанавливаю обновление" 96\n'
i=src.find(stage10)
if i<0:
    raise SystemExit('8.40 bootstrap: stage10 marker missing')
package=r'''stage "10/10 Готовлю файл для папки Программы" 96
OUT="$HOME/Desktop/ENDLUME_Studio_8.40_MAC.zip"
/bin/rm -f "$OUT"
/usr/bin/xattr -dr com.apple.quarantine "$BUILT_APP" >/dev/null 2>&1 || true
/usr/bin/codesign --force --deep --sign - "$BUILT_APP" >/dev/null 2>&1
/usr/bin/codesign --verify --deep --strict "$BUILT_APP" >/dev/null 2>&1 || fail "Подпись .app невалидна"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$BUILT_APP" "$OUT"
[[ -s "$OUT" ]] || fail "ZIP приложения не создан"
echo "@@ENDLUME_PROGRESS|100"
echo "✅ ENDLUME Studio 8.40 готова"
echo "Файл: $OUT"
echo "Распакуй ZIP и перетащи ENDLUME Studio.app в папку Программы"
/usr/bin/open -R "$OUT" >/dev/null 2>&1 || true
'''
src=src[:i]+package+'\n'

required=[
 'VERSION_EXPECTED="1.0.0-alpha.8.40"',
 'apply-youtube-fill-8-38.py',
 'apply-github-updater-8-40.py',
 'validate-release-8-40.sh',
 'ENDLUME_Studio_8.40_MAC.zip',
 'WORK_ROOT="$HOME/.endlume-local-builder"',
]
for m in required:
    if m not in src: raise SystemExit(f'8.40 bootstrap incomplete: {m}')
for forbidden in ['apply-performance-fidelity-8-39.py','repair-render-chroma-8-39.py','apply-hybrid-updater-8-39.py','validate-release-8-39.sh']:
    if forbidden in src: raise SystemExit(f'8.40 bootstrap still contains forbidden 8.39 path: {forbidden}')
Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY

chmod +x "$REAL"
/bin/bash -n "$REAL" || fail "generated bootstrap syntax failed"
for bad in apply-performance-fidelity-8-39.py repair-render-chroma-8-39.py apply-hybrid-updater-8-39.py validate-release-8-39.sh; do
  if grep -Fq "$bad" "$REAL"; then fail "8.39 path leaked into clean bootstrap: $bad"; fi
done
grep -Fq 'apply-youtube-fill-8-38.py' "$REAL" || fail "8.38 proven base missing"
grep -Fq 'apply-github-updater-8-40.py' "$REAL" || fail "native updater patch missing"
grep -Fq 'ENDLUME_Studio_8.40_MAC.zip' "$REAL" || fail "drag-drop packaging missing"

echo "✅ CLEAN 8.40 preflight passed"
echo "✅ 8.39 migration chain completely excluded"
echo "✅ Proven 8.38 gates retained"
echo "✅ Native signed updater wired"
echo "✅ Output is one drag-and-drop Mac app ZIP"
/bin/bash "$REAL"
