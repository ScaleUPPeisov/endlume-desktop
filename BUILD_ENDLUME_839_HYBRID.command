#!/bin/bash
set -Eeuo pipefail
REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
TMP="$(mktemp -d /tmp/endlume-839-hybrid.XXXXXX)"
BASE="$TMP/base.command"
PATCHED="$TMP/hybrid.command"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo "❌ ENDLUME 8.39 HYBRID: $1"; exit 1; }

[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"

gh api "repos/$REPO/contents/BUILD_ENDLUME_839_CI.command?ref=$BRANCH" --jq .content | tr -d '\n' | /usr/bin/base64 -D > "$BASE" || fail "не удалось получить 8.39 canonical builder"
[[ -s "$BASE" ]] || fail "canonical builder пуст"

python3 - "$BASE" "$PATCHED" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')
old='scripts/apply-performance-fidelity-8-39.py scripts/apply-version-8-39.py'
new='scripts/apply-performance-fidelity-8-39.py scripts/apply-hybrid-updater-8-39.py scripts/apply-version-8-39.py'
if old not in src and 'scripts/apply-hybrid-updater-8-39.py' not in src:
    raise SystemExit('8.39 hybrid: py_compile marker missing')
src=src.replace(old,new,1)
old_apply='python3 scripts/apply-performance-fidelity-8-39.py\npython3 scripts/apply-version-8-39.py\n'
new_apply='python3 scripts/apply-performance-fidelity-8-39.py\npython3 scripts/apply-hybrid-updater-8-39.py\npython3 scripts/apply-version-8-39.py\n'
if old_apply not in src and 'python3 scripts/apply-hybrid-updater-8-39.py' not in src:
    raise SystemExit('8.39 hybrid: apply marker missing')
src=src.replace(old_apply,new_apply,1)
needle=" 'apply-performance-fidelity-8-39.py',\n"
if needle in src and " 'apply-hybrid-updater-8-39.py',\n" not in src:
    src=src.replace(needle,needle+" 'apply-hybrid-updater-8-39.py',\n",1)
Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY

chmod +x "$PATCHED"
/bin/bash -n "$PATCHED" || fail "generated hybrid builder syntax failed"
grep -Fq 'python3 scripts/apply-hybrid-updater-8-39.py' "$PATCHED" || fail "hybrid updater patch не подключён"
grep -Fq 'validate-release-8-39.sh' "$PATCHED" || fail "8.39 regression gate missing"

echo "@@ENDLUME_STAGE|Hybrid Update Center: готовлю проверенную сборку"
echo "@@ENDLUME_PROGRESS|3"
/bin/bash "$PATCHED"
