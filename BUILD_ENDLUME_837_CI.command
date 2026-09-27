#!/bin/bash
set -Eeuo pipefail
REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
TMP_ROOT="$(mktemp -d /tmp/endlume-837-ci.XXXXXX)"
BASE="$TMP_ROOT/BUILD_ENDLUME_836_LOCAL.command"
PATCHED="$TMP_ROOT/BUILD_ENDLUME_837_REAL.command"
cleanup(){ rm -rf "$TMP_ROOT" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo; echo "❌ ENDLUME 8.37 CI: $1"; exit 1; }

echo "ENDLUME Studio 1.0.0-alpha.8.37 • CI BUILD"
[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon macOS runner"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"

gh api "repos/$REPO/contents/BUILD_ENDLUME_836_LOCAL.command?ref=$BRANCH" --jq .content | tr -d '\n' | /usr/bin/base64 -D > "$BASE" || fail "не удалось получить 8.36 base builder"
[[ -s "$BASE" ]] || fail "8.36 base builder пуст"
python3 - "$BASE" "$PATCHED" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')
src=src.replace('VERSION_EXPECTED="1.0.0-alpha.8.36"','VERSION_EXPECTED="1.0.0-alpha.8.37"')
src=src.replace('echo "❌ ENDLUME 8.36 остановлена ДО замены приложения"','echo "❌ ENDLUME 8.37 остановлена ДО замены приложения"')
src=src.replace('│ 8.36 • 1080p Fidelity Lock • clean first frame            │','│ 8.37 • 1080p Fidelity Lock • Remote Update Center         │')

apply_marker='python3 scripts/apply-version-8-36.py\n'
addition='''python3 -m py_compile scripts/repair-settings-updater-8-37.py scripts/apply-remote-updater-8-37.py scripts/apply-version-8-37.py
python3 scripts/repair-settings-updater-8-37.py
python3 scripts/apply-remote-updater-8-37.py
python3 scripts/apply-version-8-37.py
'''
if apply_marker not in src: raise SystemExit('8.37 CI: apply-version-8-36 marker missing')
src=src.replace(apply_marker,apply_marker+addition,1)

old_stage='''chmod +x scripts/validate-release-8-36.sh
scripts/validate-release-8-36.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs
'''
new_stage='''chmod +x scripts/validate-release-8-36.sh scripts/validate-release-8-37.sh
scripts/validate-release-8-36.sh "$FFMPEG" "$FFPROBE"
scripts/validate-release-8-37.sh
node scripts/validate-motion-ui.mjs
'''
if old_stage not in src: raise SystemExit('8.37 CI: validator marker missing')
src=src.replace(old_stage,new_stage,1)

stage10='stage "10/10 Устанавливаю обновление" 96\n'
ci='''if [[ -n "${ENDLUME_CI_ARTIFACT_DIR:-}" ]]; then
  mkdir -p "$ENDLUME_CI_ARTIFACT_DIR"
  ASSET="${ENDLUME_CI_ASSET_NAME:-ENDLUME-Studio-1.0.0-alpha.8.37-macos-arm64.zip}"
  /usr/bin/ditto -c -k --keepParent "$BUILT_APP" "$ENDLUME_CI_ARTIFACT_DIR/$ASSET"
  (cd "$ENDLUME_CI_ARTIFACT_DIR" && /usr/bin/shasum -a 256 "$ASSET" > "$ASSET.sha256")
  echo "@@ENDLUME_STAGE|CI artifact ready"
  echo "@@ENDLUME_PROGRESS|100"
  exit 0
fi
'''
if stage10 not in src: raise SystemExit('8.37 CI: stage10 marker missing')
src=src.replace(stage10,ci+stage10,1)

for marker in ['repair-settings-updater-8-37.py','apply-remote-updater-8-37.py','validate-release-8-37.sh','VERSION_EXPECTED="1.0.0-alpha.8.37"','ENDLUME_CI_ARTIFACT_DIR','assert_no_tauri_appledouble']:
    if marker not in src: raise SystemExit(f'8.37 CI incomplete: {marker}')
if "'VERSION_EXPECTED=\"1.0.0-alpha.8.36\"'" in src:
    raise SystemExit('8.37 CI: stale 8.36 required self-gate survived')
Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY
chmod +x "$PATCHED"
/bin/bash -n "$PATCHED" || fail "generated CI builder syntax failed"
grep -Fq 'repair-settings-updater-8-37.py' "$PATCHED" || fail "Settings migration bridge missing"
grep -Fq 'VERSION_EXPECTED="1.0.0-alpha.8.37"' "$PATCHED" || fail "8.37 version gate missing"
grep -Fq 'ENDLUME_CI_ARTIFACT_DIR' "$PATCHED" || fail "CI artifact mode missing"
if grep -Fq "'VERSION_EXPECTED=\"1.0.0-alpha.8.36\"'" "$PATCHED"; then fail "stale 8.36 self-gate survived"; fi
/bin/bash "$PATCHED"
