#!/bin/bash
set -Eeuo pipefail
REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
TMP_ROOT="$(mktemp -d /tmp/endlume-838.XXXXXX)"
BASE="$TMP_ROOT/BUILD_ENDLUME_836_LOCAL.command"
PATCHED="$TMP_ROOT/BUILD_ENDLUME_838_REAL.command"
BUILD_LOG="$HOME/Desktop/ENDLUME-local-build.log"
cleanup(){ rm -rf "$TMP_ROOT" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo; echo "❌ ENDLUME 8.38 installer: $1"; exit 1; }

echo "ENDLUME Studio 1.0.0-alpha.8.38"
echo "YouTube Fill 16:9 • NO BLACK BARS • exact 1920x1080 • original MP3"
echo
[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"

gh api "repos/$REPO/contents/BUILD_ENDLUME_836_LOCAL.command?ref=$BRANCH" --jq .content | tr -d '\n' | /usr/bin/base64 -D > "$BASE" || fail "не удалось получить 8.36 base builder"
[[ -s "$BASE" ]] || fail "8.36 base builder пуст"

python3 - "$BASE" "$PATCHED" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')

# Final version and visible diagnostics.
src=src.replace('VERSION_EXPECTED="1.0.0-alpha.8.36"','VERSION_EXPECTED="1.0.0-alpha.8.38"')
src=src.replace('echo "❌ ENDLUME 8.36 остановлена ДО замены приложения"','echo "❌ ENDLUME 8.38 остановлена ДО замены приложения"')
src=src.replace('│ 8.36 • 1080p Fidelity Lock • clean first frame            │','│ 8.38 • YouTube Fill 16:9 • NO BLACK BARS                 │')

# Never build the bootstrap on /Volumes/*; keep it on the internal APFS volume.
needle="src=src.replace('SRC=\"$WORK_ROOT/endlume-desktop-8.33\"','SRC=\"$WORK_ROOT/endlume-desktop-8.36\"',1)\n"
if needle not in src:
    raise SystemExit('8.38 builder: 8.36 work-root transform marker missing')
internal="src=src.replace('WORK_ROOT=\"$(choose_work_root)\"','WORK_ROOT=\"$HOME/.endlume-local-builder\"',1)\n"
src=src.replace(needle,needle+internal,1)

# Deterministic version chain. Validate each older release BEFORE applying the next policy.
apply_marker='python3 scripts/apply-version-8-36.py\n'
addition='''chmod +x scripts/validate-release-8-36.sh
scripts/validate-release-8-36.sh "$FFMPEG" "$FFPROBE"
python3 -m py_compile scripts/repair-settings-updater-8-37.py scripts/apply-remote-updater-8-37.py scripts/apply-version-8-37.py scripts/apply-youtube-fill-8-38.py scripts/apply-version-8-38.py
python3 scripts/repair-settings-updater-8-37.py
python3 scripts/apply-remote-updater-8-37.py
python3 scripts/apply-version-8-37.py
chmod +x scripts/validate-release-8-37.sh
scripts/validate-release-8-37.sh
python3 scripts/apply-youtube-fill-8-38.py
python3 scripts/apply-version-8-38.py
'''
if apply_marker not in src:
    raise SystemExit('8.38 builder: apply-version-8-36 marker missing')
src=src.replace(apply_marker,apply_marker+addition,1)

# Final acceptance: only the new 8.38 policy after all patches are present.
old_stage='''stage "7/10 Гоняю финальный 1080p Fidelity / Audio / Effects regression" 58
chmod +x scripts/validate-release-8-36.sh
scripts/validate-release-8-36.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs
'''
new_stage='''stage "7/10 Проверяю YouTube Fill 16:9 / No Black Bars" 58
chmod +x scripts/validate-release-8-38.sh
scripts/validate-release-8-38.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs
'''
if old_stage not in src:
    raise SystemExit('8.38 builder: final stage marker missing')
src=src.replace(old_stage,new_stage,1)

required=[
    'VERSION_EXPECTED="1.0.0-alpha.8.38"',
    'WORK_ROOT="$HOME/.endlume-local-builder"',
    'repair-settings-updater-8-37.py',
    'apply-remote-updater-8-37.py',
    'apply-youtube-fill-8-38.py',
    'apply-version-8-38.py',
    'validate-release-8-38.sh',
    'assert_no_tauri_appledouble',
    'apply-fidelity-1080p-8-36.py',
]
for marker in required:
    if marker not in src:
        raise SystemExit(f'8.38 builder incomplete: {marker}')
Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY

chmod +x "$PATCHED"
/bin/bash -n "$PATCHED" || fail "generated 8.38 builder syntax failed"
grep -Fq 'VERSION_EXPECTED="1.0.0-alpha.8.38"' "$PATCHED" || fail "8.38 version gate missing"
grep -Fq 'apply-youtube-fill-8-38.py' "$PATCHED" || fail "No Black Bars patch missing"
grep -Fq 'validate-release-8-38.sh' "$PATCHED" || fail "No Black Bars acceptance gate missing"
grep -Fq 'WORK_ROOT="$HOME/.endlume-local-builder"' "$PATCHED" || fail "builder всё ещё может выбрать внешний диск"

echo "✅ 8.38 builder сформирован"
echo "✅ Exact 1920x1080 + increase/crop + NO PAD встроены"
echo "✅ Square / portrait / ultrawide no-black-bars gate встроен"
echo "✅ Сборка идёт на внутреннем SSD"
: > "$BUILD_LOG"
/bin/bash "$PATCHED"
