#!/bin/bash
set -Eeuo pipefail
REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
TMP_ROOT="$(mktemp -d /tmp/endlume-837-bootstrap.XXXXXX)"
BASE="$TMP_ROOT/BUILD_ENDLUME_836_LOCAL.command"
PATCHED="$TMP_ROOT/BUILD_ENDLUME_837_REAL.command"
cleanup(){ rm -rf "$TMP_ROOT" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo; echo "❌ ENDLUME 8.37 bootstrap: $1"; exit 1; }

echo "ENDLUME Studio 1.0.0-alpha.8.37"
echo "ONE-TIME IN-APP BOOTSTRAP → Remote Update Center"
[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"

gh api "repos/$REPO/contents/BUILD_ENDLUME_836_LOCAL.command?ref=$BRANCH" --jq .content | tr -d '\n' | /usr/bin/base64 -D > "$BASE" || fail "не удалось получить 8.36 base builder"
python3 - "$BASE" "$PATCHED" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')
src=src.replace('1.0.0-alpha.8.36','1.0.0-alpha.8.37')
src=src.replace('ENDLUME 8.36 installer','ENDLUME 8.37 bootstrap')
src=src.replace('канонический 8.36','канонический 8.37 bootstrap')
old="""python3 scripts/apply-fidelity-1080p-8-36.py
python3 scripts/apply-version-8-36.py
'''"""
new="""python3 scripts/apply-fidelity-1080p-8-36.py
python3 scripts/apply-version-8-36.py
python3 -m py_compile scripts/apply-remote-updater-8-37.py scripts/apply-version-8-37.py
python3 scripts/apply-remote-updater-8-37.py
python3 scripts/apply-version-8-37.py
'''"""
if old not in src: raise SystemExit('8.37 bootstrap: apply marker missing')
src=src.replace(old,new,1)
old_stage='''chmod +x scripts/validate-release-8-36.sh
scripts/validate-release-8-36.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs
'''
new_stage='''chmod +x scripts/validate-release-8-36.sh scripts/validate-release-8-37.sh
scripts/validate-release-8-36.sh "$FFMPEG" "$FFPROBE"
scripts/validate-release-8-37.sh
node scripts/validate-motion-ui.mjs
'''
if old_stage not in src: raise SystemExit('8.37 bootstrap: validator marker missing')
src=src.replace(old_stage,new_stage,1)
for m in ['apply-remote-updater-8-37.py','validate-release-8-37.sh','VERSION_EXPECTED="1.0.0-alpha.8.37"']:
    if m not in src: raise SystemExit(f'8.37 bootstrap incomplete: {m}')
Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY
chmod +x "$PATCHED"
/bin/bash -n "$PATCHED" || fail "generated bootstrap syntax failed"
echo "✅ Bootstrap проверен. Дальше обновления управляются из Настроек ENDLUME."
/bin/bash "$PATCHED"
