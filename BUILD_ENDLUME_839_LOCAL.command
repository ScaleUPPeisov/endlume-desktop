#!/bin/bash
set -Eeuo pipefail
REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
TMP_ROOT="$(mktemp -d /tmp/endlume-839-direct.XXXXXX)"
BASE="$TMP_ROOT/BUILD_ENDLUME_833_LOCAL.command"
PATCHED="$TMP_ROOT/BUILD_ENDLUME_839_REAL.command"
cleanup(){ rm -rf "$TMP_ROOT" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo; echo "❌ ENDLUME 8.39 DIRECT: $1"; exit 1; }

echo "ENDLUME Studio 1.0.0-alpha.8.39"
echo "DIRECT BASE • TRUE 60 FPS • UI stability • crossfade/no-gap • chroma despill"
echo
[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"

gh api "repos/$REPO/contents/BUILD_ENDLUME_833_LOCAL.command?ref=$BRANCH" --jq .content | tr -d '\n' | /usr/bin/base64 -D > "$BASE" || fail "не удалось получить proven 8.33 base builder"
[[ -s "$BASE" ]] || fail "8.33 base builder пуст"

python3 - "$BASE" "$PATCHED" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')

# Final identity. The real stage 10 is present in this base from the start.
src=src.replace('VERSION_EXPECTED="1.0.0-alpha.8.33"','VERSION_EXPECTED="1.0.0-alpha.8.39"',1)
src=src.replace('echo "❌ ENDLUME 8.33 остановлена ДО замены приложения"','echo "❌ ENDLUME 8.39 остановлена ДО замены приложения"',1)
src=src.replace('SRC="$WORK_ROOT/endlume-desktop-8.33"','SRC="$WORK_ROOT/endlume-desktop-8.39"',1)
src=src.replace('│ 8.33 • SSD workdir • Fast Fidelity • Preview repair       │','│ 8.39 • TRUE 60 FPS • STABILITY • AUDIO • CHROMA          │',1)
src=src.replace('WORK_ROOT="$(choose_work_root)"','WORK_ROOT="$HOME/.endlume-local-builder"',1)

# Keep build metadata clean on macOS and reject AppleDouble before Tauri parses it.
src=src.replace('set -Eeuo pipefail\n\nAPP_NAME=','set -Eeuo pipefail\nexport COPYFILE_DISABLE=1\nexport COPY_EXTENDED_ATTRIBUTES_DISABLE=1\n\nAPP_NAME=',1)
shield_marker='# Prefer the writable external volume with the most free space.'
shield='''sanitize_build_appledouble(){
  [[ -d "${SRC:-}" ]] || return 0
  /usr/bin/find "$SRC" \\
    \\( -path "$SRC/.git" -o -path "$SRC/node_modules" -o -path "$SRC/src-tauri/target" \\) -prune -o \\
    -type f -name '._*' -exec /bin/rm -f {} + 2>/dev/null || true
  for d in "$SRC/src-tauri/capabilities" "$SRC/src-tauri/icons" "$SRC/src-tauri/binaries"; do
    [[ -d "$d" ]] || continue
    /usr/bin/find "$d" -type f -name '._*' -exec /bin/rm -f {} + 2>/dev/null || true
  done
}
assert_no_tauri_appledouble(){
  sanitize_build_appledouble
  local bad=""
  if [[ -d "$SRC/src-tauri/capabilities" ]]; then bad="$(/usr/bin/find "$SRC/src-tauri/capabilities" -type f -name '._*' -print -quit 2>/dev/null || true)"; fi
  [[ -z "$bad" ]] || fail "AppleDouble sidecar остался в Tauri capabilities: $bad"
}

'''
if shield_marker not in src:
    raise SystemExit('8.39 direct: work-root marker missing')
src=src.replace(shield_marker,shield+shield_marker,1)

clone='gh repo clone "$REPO" "$SRC" -- --branch "$BRANCH" --single-branch\ncd "$SRC"\n'
if clone not in src:
    raise SystemExit('8.39 direct: clone marker missing')
src=src.replace(clone,clone+'sanitize_build_appledouble\n',1)
src=src.replace('npm install --no-audit --no-fund\n','npm install --no-audit --no-fund\nsanitize_build_appledouble\n',1)

# Normalize the proven 8.33 migration before replaying it.
speed='python3 scripts/apply-speed-fidelity-8-33.py\n'
repair='''python3 -m py_compile scripts/repair-speed-workdir-8-33.py
python3 scripts/repair-speed-workdir-8-33.py
'''
if speed not in src:
    raise SystemExit('8.39 direct: 8.33 speed marker missing')
src=src.replace(speed,repair+speed,1)

# One deterministic policy chain: 8.33 -> 8.34 -> 8.35 -> 8.36 -> 8.37 -> 8.38 -> 8.39.
marker='python3 scripts/apply-version-8-33.py\n'
addition='''python3 -m py_compile scripts/apply-stability-8-34.py scripts/apply-version-8-34.py scripts/apply-strict-fidelity-8-35.py scripts/apply-version-8-35.py scripts/repair-strict-store-8-35.py scripts/apply-fidelity-1080p-8-36.py scripts/apply-version-8-36.py scripts/repair-settings-updater-8-37.py scripts/apply-remote-updater-8-37.py scripts/apply-version-8-37.py scripts/apply-youtube-fill-8-38.py scripts/apply-version-8-38.py scripts/apply-performance-fidelity-8-39.py scripts/apply-hybrid-updater-8-39.py scripts/apply-version-8-39.py
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
python3 scripts/apply-performance-fidelity-8-39.py
python3 scripts/apply-hybrid-updater-8-39.py
python3 scripts/apply-version-8-39.py
'''
if marker not in src:
    raise SystemExit('8.39 direct: apply-version-8-33 marker missing')
src=src.replace(marker,marker+addition,1)

# Tauri manifest shield immediately before Rust and final app build.
cargo='stage "6.7/10 Проверяю Rust" 50\ncargo check --manifest-path src-tauri/Cargo.toml --target aarch64-apple-darwin\n'
if cargo not in src:
    raise SystemExit('8.39 direct: cargo marker missing')
src=src.replace(cargo,'stage "6.7/10 Проверяю Rust" 50\nassert_no_tauri_appledouble\ncargo check --manifest-path src-tauri/Cargo.toml --target aarch64-apple-darwin\n',1)

# Only final policy gate changes. Stage 9 and Stage 10 are preserved from proven base.
old_stage='''stage "7/10 Гоняю Effects / Subscribe / Audio / SSD / Fast Fidelity regression" 58
chmod +x scripts/validate-release-8-33.sh
scripts/validate-release-8-33.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs
'''
new_stage='''stage "7/10 Проверяю 60 FPS / UI / Crossfade / Chroma / Speed-Size" 58
chmod +x scripts/validate-release-8-39.sh
scripts/validate-release-8-39.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs
'''
if old_stage not in src:
    raise SystemExit('8.39 direct: stage-7 marker missing')
src=src.replace(old_stage,new_stage,1)

build='stage "9/10 Собираю ENDLUME Studio.app" 80\nnpx tauri build --target aarch64-apple-darwin --bundles app --config src-tauri/tauri.local.conf.json\n'
if build not in src:
    raise SystemExit('8.39 direct: tauri build marker missing')
src=src.replace(build,'stage "9/10 Собираю ENDLUME Studio.app" 80\nassert_no_tauri_appledouble\nnpx tauri build --target aarch64-apple-darwin --bundles app --config src-tauri/tauri.local.conf.json\n',1)

built='[[ -d "$BUILT_APP" ]] || fail "Tauri не создал .app"\n'
if built not in src:
    raise SystemExit('8.39 direct: built-app marker missing')
src=src.replace(built,built+"/usr/bin/find \"$BUILT_APP\" -type f -name '._*' -exec /bin/rm -f {} + 2>/dev/null || true\n",1)

cache='/bin/rm -rf "$HOME/Library/Caches/studio.endlume.desktop/render-work" >/dev/null 2>&1 || true\n'
if cache in src:
    src=src.replace(cache,cache+'/bin/rm -rf "$HOME/Library/Caches/studio.endlume.desktop/live-preview-v5" "$HOME/Library/Caches/studio.endlume.desktop/live-preview-v6" >/dev/null 2>&1 || true\n',1)

required=[
 'VERSION_EXPECTED="1.0.0-alpha.8.39"',
 'WORK_ROOT="$HOME/.endlume-local-builder"',
 'repair-speed-workdir-8-33.py',
 'apply-fidelity-1080p-8-36.py',
 'apply-youtube-fill-8-38.py',
 'apply-performance-fidelity-8-39.py',
 'apply-hybrid-updater-8-39.py',
 'validate-release-8-39.sh',
 'stage "10/10 Устанавливаю обновление" 96',
 'assert_no_tauri_appledouble\ncargo check',
 'assert_no_tauri_appledouble\nnpx tauri build',
]
for m in required:
    if m not in src:
        raise SystemExit(f'8.39 direct incomplete: {m}')
if 'ENDLUME_CI_ARTIFACT_DIR' in src:
    raise SystemExit('8.39 direct: CI artifact mutation must not exist')
Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY

chmod +x "$PATCHED"
/bin/bash -n "$PATCHED" || fail "generated 8.39 direct builder syntax failed"
grep -Fq 'VERSION_EXPECTED="1.0.0-alpha.8.39"' "$PATCHED" || fail "8.39 version gate missing"
grep -Fq 'stage "10/10 Устанавливаю обновление" 96' "$PATCHED" || fail "real stage10 install block missing"
grep -Fq 'apply-hybrid-updater-8-39.py' "$PATCHED" || fail "Hybrid Update Center patch missing"
grep -Fq 'validate-release-8-39.sh' "$PATCHED" || fail "8.39 acceptance gate missing"
grep -Fq 'WORK_ROOT="$HOME/.endlume-local-builder"' "$PATCHED" || fail "external build root survived"
if grep -Fq 'ENDLUME_CI_ARTIFACT_DIR' "$PATCHED"; then fail "CI artifact mutation leaked into direct installer"; fi

echo "✅ DIRECT 8.39 preflight passed"
echo "✅ Real stage 10 exists before build starts"
echo "✅ No wrapper nesting and no CI stage10 mutation"
echo "✅ Hybrid Update Center will be installed for future updates"
/bin/bash "$PATCHED"
