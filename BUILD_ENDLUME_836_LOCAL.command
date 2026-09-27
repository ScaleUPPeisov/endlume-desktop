#!/bin/bash
set -Eeuo pipefail

REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
TMP_ROOT="$(mktemp -d /tmp/endlume-836.XXXXXX)"
BASE="$TMP_ROOT/BUILD_ENDLUME_833_LOCAL.command"
PATCHED="$TMP_ROOT/BUILD_ENDLUME_836_REAL.command"
cleanup(){ rm -rf "$TMP_ROOT" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo; echo "❌ ENDLUME 8.36 installer: $1"; exit 1; }

echo "ENDLUME Studio 1.0.0-alpha.8.36"
echo "1080p Fidelity Lock • clean first frame • original MP3 • <=1 GB target"
echo
[[ "$(uname -s)" == "Darwin" ]] || fail "нужна macOS"
[[ "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon"

if ! command -v gh >/dev/null 2>&1; then
  if ! command -v brew >/dev/null 2>&1; then
    NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || fail "не удалось установить Homebrew"
    [[ -x /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"
  fi
  brew install gh || fail "не удалось установить GitHub CLI"
fi
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован. Выполни: gh auth login"

echo "Получаю один базовый builder 8.33 и формирую канонический 8.36 без цепочки wrapper→wrapper…"
gh api "repos/$REPO/contents/BUILD_ENDLUME_833_LOCAL.command?ref=$BRANCH" --jq .content | tr -d '\n' | /usr/bin/base64 -D > "$BASE" || fail "не удалось получить базовый builder"
[[ -s "$BASE" ]] || fail "базовый builder пуст"

python3 - "$BASE" "$PATCHED" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')

src=src.replace('VERSION_EXPECTED="1.0.0-alpha.8.33"','VERSION_EXPECTED="1.0.0-alpha.8.36"',1)
src=src.replace('echo "❌ ENDLUME 8.33 остановлена ДО замены приложения"','echo "❌ ENDLUME 8.36 остановлена ДО замены приложения"',1)
src=src.replace('SRC="$WORK_ROOT/endlume-desktop-8.33"','SRC="$WORK_ROOT/endlume-desktop-8.36"',1)
src=src.replace('│ 8.33 • SSD workdir • Fast Fidelity • Preview repair       │','│ 8.36 • 1080p Fidelity Lock • clean first frame            │',1)

# External-drive AppleDouble build shield.
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
if shield_marker not in src: raise SystemExit('8.36 builder: work-root marker missing')
src=src.replace(shield_marker,shield+shield_marker,1)

clone='gh repo clone "$REPO" "$SRC" -- --branch "$BRANCH" --single-branch\ncd "$SRC"\n'
if clone not in src: raise SystemExit('8.36 builder: clone marker missing')
src=src.replace(clone,clone+'sanitize_build_appledouble\n',1)
src=src.replace('npm install --no-audit --no-fund\n','npm install --no-audit --no-fund\nsanitize_build_appledouble\n',1)

# Normalize the old 8.25 workdir helper before 8.33 replays its SSD migration.
work='python3 scripts/apply-speed-fidelity-8-33.py\n'
repair='''python3 -m py_compile scripts/repair-speed-workdir-8-33.py
python3 scripts/repair-speed-workdir-8-33.py
'''
if work not in src: raise SystemExit('8.36 builder: 8.33 speed marker missing')
src=src.replace(work,repair+work,1)

# One deterministic apply chain: 8.33 -> 8.34 shield -> 8.35 audio/runtime -> 8.36 output/quality.
marker='python3 scripts/apply-version-8-33.py\n'
addition='''python3 -m py_compile scripts/apply-stability-8-34.py scripts/apply-version-8-34.py scripts/apply-strict-fidelity-8-35.py scripts/apply-version-8-35.py scripts/repair-strict-store-8-35.py scripts/apply-fidelity-1080p-8-36.py scripts/apply-version-8-36.py
python3 scripts/apply-stability-8-34.py
python3 scripts/apply-version-8-34.py
python3 scripts/apply-strict-fidelity-8-35.py
python3 scripts/apply-version-8-35.py
python3 scripts/repair-strict-store-8-35.py
# Backward regressions run BEFORE 8.36 changes the quality policy.
chmod +x scripts/validate-release-8-33.sh scripts/validate-release-8-34.sh
scripts/validate-release-8-33.sh "$FFMPEG" "$FFPROBE"
scripts/validate-release-8-34.sh "$FFMPEG" "$FFPROBE"
python3 scripts/apply-fidelity-1080p-8-36.py
python3 scripts/apply-version-8-36.py
'''
if marker not in src: raise SystemExit('8.36 builder: apply marker missing')
src=src.replace(marker,marker+addition,1)

# Sanitize Tauri manifests immediately before Rust and final Tauri build.
cargo='stage "6.7/10 Проверяю Rust" 50\ncargo check --manifest-path src-tauri/Cargo.toml --target aarch64-apple-darwin\n'
if cargo not in src: raise SystemExit('8.36 builder: cargo marker missing')
src=src.replace(cargo,'stage "6.7/10 Проверяю Rust" 50\nassert_no_tauri_appledouble\ncargo check --manifest-path src-tauri/Cargo.toml --target aarch64-apple-darwin\n',1)

# Replace the legacy stage-7 validator with the final 8.36 acceptance gate.
old_stage='''stage "7/10 Гоняю Effects / Subscribe / Audio / SSD / Fast Fidelity regression" 58
chmod +x scripts/validate-release-8-33.sh
scripts/validate-release-8-33.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs
'''
new_stage='''stage "7/10 Гоняю финальный 1080p Fidelity / Audio / Effects regression" 58
chmod +x scripts/validate-release-8-36.sh
scripts/validate-release-8-36.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs
'''
if old_stage not in src: raise SystemExit('8.36 builder: stage-7 marker missing')
src=src.replace(old_stage,new_stage,1)

build='stage "9/10 Собираю ENDLUME Studio.app" 80\nnpx tauri build --target aarch64-apple-darwin --bundles app --config src-tauri/tauri.local.conf.json\n'
if build not in src: raise SystemExit('8.36 builder: tauri-build marker missing')
src=src.replace(build,'stage "9/10 Собираю ENDLUME Studio.app" 80\nassert_no_tauri_appledouble\nnpx tauri build --target aarch64-apple-darwin --bundles app --config src-tauri/tauri.local.conf.json\n',1)

built='[[ -d "$BUILT_APP" ]] || fail "Tauri не создал .app"\n'
src=src.replace(built,built+"/usr/bin/find \"$BUILT_APP\" -type f -name '._*' -exec /bin/rm -f {} + 2>/dev/null || true\n",1)

# Clear poisoned preview caches after successful installation path is prepared.
cache='/bin/rm -rf "$HOME/Library/Caches/studio.endlume.desktop/render-work" >/dev/null 2>&1 || true\n'
src=src.replace(cache,cache+'/bin/rm -rf "$HOME/Library/Caches/studio.endlume.desktop/live-preview-v5" "$HOME/Library/Caches/studio.endlume.desktop/live-preview-v6" >/dev/null 2>&1 || true\n',1)

required=[
 'repair-speed-workdir-8-33.py',
 'apply-fidelity-1080p-8-36.py',
 'validate-release-8-36.sh',
 'assert_no_tauri_appledouble\ncargo check',
 'assert_no_tauri_appledouble\nnpx tauri build',
 'VERSION_EXPECTED="1.0.0-alpha.8.36"',
]
for m in required:
    if m not in src: raise SystemExit(f'8.36 builder incomplete: {m}')
Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY

chmod +x "$PATCHED"
/bin/bash -n "$PATCHED" || fail "сформированный builder не прошёл shell syntax"
grep -Fq 'apply-fidelity-1080p-8-36.py' "$PATCHED" || fail "8.36 fidelity patch потерян"
grep -Fq 'assert_no_tauri_appledouble' "$PATCHED" || fail "AppleDouble build shield потерян"
echo "✅ Канонический builder: одна цепочка, без 8.34→8.35 wrapper nesting"
echo "✅ Exact 1920×1080 + x265 first-frame quality gate встроены"
echo "✅ External-drive AppleDouble shield встроен перед Rust и Tauri"
/bin/bash "$PATCHED"
