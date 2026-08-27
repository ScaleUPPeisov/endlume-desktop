#!/bin/bash
set -Eeuo pipefail
REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
TMP_ROOT="$(mktemp -d /tmp/endlume-837-bootstrap.XXXXXX)"
BASE="$TMP_ROOT/BUILD_ENDLUME_836_LOCAL.command"
PATCHED="$TMP_ROOT/BUILD_ENDLUME_837_REAL.command"
VALIDATOR="$TMP_ROOT/validate-release-8-36.sh"
cleanup(){ rm -rf "$TMP_ROOT" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo; echo "❌ ENDLUME 8.37 bootstrap: $1"; exit 1; }

echo "ENDLUME Studio 1.0.0-alpha.8.37"
echo "ONE-TIME IN-APP BOOTSTRAP → Remote Update Center"
[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"

# Preflight the exact validator that previously broke on /Volumes/TOSHIBA EXT.
gh api "repos/$REPO/contents/scripts/validate-release-8-36.sh?ref=$BRANCH" --jq .content | tr -d '\n' | /usr/bin/base64 -D > "$VALIDATOR" || fail "не удалось получить validator 8.36"
grep -Fq 'DIM="$("$FFPROBE"' "$VALIDATOR" || fail "release validator всё ещё ломает пути с пробелами"
grep -Fq 'VBR="$("$FFPROBE"' "$VALIDATOR" || fail "release validator bitrate всё ещё ломает пути с пробелами"
echo "✅ Path-with-spaces validator исправлен"

gh api "repos/$REPO/contents/BUILD_ENDLUME_836_LOCAL.command?ref=$BRANCH" --jq .content | tr -d '\n' | /usr/bin/base64 -D > "$BASE" || fail "не удалось получить 8.36 base builder"
[[ -s "$BASE" ]] || fail "8.36 base builder пуст"

python3 - "$BASE" "$PATCHED" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')

# Keep the proven 8.36 chain, but make the final package 8.37 and inject the
# Remote Update Center only after 8.36 Fidelity Lock has been applied.
src=src.replace('VERSION_EXPECTED="1.0.0-alpha.8.36"','VERSION_EXPECTED="1.0.0-alpha.8.37"',1)
src=src.replace('echo "❌ ENDLUME 8.36 остановлена ДО замены приложения"','echo "❌ ENDLUME 8.37 остановлена ДО замены приложения"',1)
src=src.replace('│ 8.36 • 1080p Fidelity Lock • clean first frame            │','│ 8.37 • 1080p Fidelity Lock • Remote Update Center         │',1)

apply_marker='python3 scripts/apply-version-8-36.py\n'
addition='''python3 -m py_compile scripts/apply-remote-updater-8-37.py scripts/apply-version-8-37.py
python3 scripts/apply-remote-updater-8-37.py
python3 scripts/apply-version-8-37.py
'''
if apply_marker not in src:
    raise SystemExit('8.37 bootstrap: apply-version-8-36 marker missing')
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
if old_stage not in src:
    raise SystemExit('8.37 bootstrap: final validator marker missing')
src=src.replace(old_stage,new_stage,1)

required=[
    'VERSION_EXPECTED="1.0.0-alpha.8.37"',
    'apply-remote-updater-8-37.py',
    'apply-version-8-37.py',
    'validate-release-8-37.sh',
    'assert_no_tauri_appledouble',
    'apply-fidelity-1080p-8-36.py',
]
for marker in required:
    if marker not in src:
        raise SystemExit(f'8.37 bootstrap incomplete: {marker}')
Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY

chmod +x "$PATCHED"
/bin/bash -n "$PATCHED" || fail "generated bootstrap syntax failed"
grep -Fq 'VERSION_EXPECTED="1.0.0-alpha.8.37"' "$PATCHED" || fail "8.37 final version gate missing"
grep -Fq 'apply-remote-updater-8-37.py' "$PATCHED" || fail "Remote Update Center patch missing"
grep -Fq 'validate-release-8-37.sh' "$PATCHED" || fail "8.37 acceptance gate missing"
echo "✅ Bootstrap 8.37 проверен до запуска тяжёлой сборки"
echo "✅ После установки следующие обновления — готовыми бинарниками из Настроек"
/bin/bash "$PATCHED"
