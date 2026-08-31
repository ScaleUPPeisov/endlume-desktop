#!/bin/bash
set -Eeuo pipefail
REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
TMP="$(mktemp -d /tmp/endlume-839-final.XXXXXX)"
BASE="$TMP/BUILD_ENDLUME_839_LOCAL.command"
PATCHED="$TMP/BUILD_ENDLUME_839_FINAL_REAL.command"
VALIDATOR="$TMP/validate-release-8-38.sh"
REPAIR="$TMP/repair-render-chroma-8-39.py"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo; echo "❌ ENDLUME 8.39 FINAL: $1"; exit 1; }

echo "ENDLUME Studio 1.0.0-alpha.8.39 • FINAL FIX2"
echo "Direct 8.33 base • fixed 8.38 validator • normalized chroma • real stage 10"
echo
[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"

gh api -H "Accept: application/vnd.github.raw+json" "/repos/$REPO/contents/BUILD_ENDLUME_839_LOCAL.command?ref=$BRANCH" > "$BASE" || fail "не удалось получить direct 8.39 builder"
gh api -H "Accept: application/vnd.github.raw+json" "/repos/$REPO/contents/scripts/validate-release-8-38.sh?ref=$BRANCH" > "$VALIDATOR" || fail "не удалось получить 8.38 validator"
gh api -H "Accept: application/vnd.github.raw+json" "/repos/$REPO/contents/scripts/repair-render-chroma-8-39.py?ref=$BRANCH" > "$REPAIR" || fail "не удалось получить chroma repair"
[[ -s "$BASE" && -s "$VALIDATOR" && -s "$REPAIR" ]] || fail "один из preflight-файлов пуст"
/bin/bash -n "$BASE" || fail "direct builder shell syntax failed"
/bin/bash -n "$VALIDATOR" || fail "8.38 validator shell syntax failed"
python3 -m py_compile "$REPAIR" || fail "chroma repair Python syntax failed"

# Exact regressions from the previous user runs.
grep -Fq 'local name="$1"' "$VALIDATOR" || fail "8.38 validator still has old nounset declaration"
grep -Fq 'local size="$2"' "$VALIDATOR" || fail "8.38 validator size declaration missing"
grep -Fq 'local out="$TMP/$name.png"' "$VALIDATOR" || fail "8.38 validator output declaration missing"
grep -Fq 'stage "10/10 Устанавливаю обновление" 96' "$BASE" || fail "real stage 10 preflight missing"
grep -Fq 'BUILD_ENDLUME_833_LOCAL.command' "$BASE" || fail "direct proven base missing"
grep -Fq 'apply-performance-fidelity-8-39.py' "$BASE" || fail "8.39 performance patch missing"
grep -Fq 'apply-hybrid-updater-8-39.py' "$BASE" || fail "Hybrid Update Center patch missing"
if grep -Fq 'BUILD_ENDLUME_839_CI.command' "$BASE"; then fail "old CI wrapper returned"; fi

python3 - "$BASE" "$PATCHED" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text(encoding='utf-8')
old='python3 scripts/apply-performance-fidelity-8-39.py\n'
new='python3 scripts/repair-render-chroma-8-39.py\npython3 scripts/apply-performance-fidelity-8-39.py\n'
if old not in s:
    raise SystemExit('8.39 FINAL: performance apply marker missing')
s=s.replace(old,new,1)
old_compile='scripts/apply-performance-fidelity-8-39.py scripts/apply-hybrid-updater-8-39.py scripts/apply-version-8-39.py'
new_compile='scripts/repair-render-chroma-8-39.py scripts/apply-performance-fidelity-8-39.py scripts/apply-hybrid-updater-8-39.py scripts/apply-version-8-39.py'
if old_compile in s:
    s=s.replace(old_compile,new_compile,1)
for marker in [
    'python3 scripts/repair-render-chroma-8-39.py',
    'python3 scripts/apply-performance-fidelity-8-39.py',
    'validate-release-8-39.sh',
    'stage "10/10 Устанавливаю обновление" 96',
    'WORK_ROOT="$HOME/.endlume-local-builder"',
]:
    if marker not in s:
        raise SystemExit(f'8.39 FINAL incomplete: {marker}')
Path(sys.argv[2]).write_text(s,encoding='utf-8')
PY

chmod +x "$PATCHED"
/bin/bash -n "$PATCHED" || fail "generated final builder shell syntax failed"
grep -Fq 'python3 scripts/repair-render-chroma-8-39.py' "$PATCHED" || fail "chroma repair not wired"
grep -Fq 'stage "10/10 Устанавливаю обновление" 96' "$PATCHED" || fail "stage 10 disappeared after FINAL patch"
# CI-artifact guard belongs here: check the generated executable builder, not the generator source.
if grep -Fq 'ENDLUME_CI_ARTIFACT_DIR=' "$PATCHED"; then fail "generated builder contains active CI artifact mutation"; fi

echo "✅ Previous failure #1 blocked: 8.38 nounset validator fixed"
echo "✅ Previous failure #2 blocked: render chroma normalized before 8.39 patch"
echo "✅ Previous failure #3 blocked: false CI self-check removed"
echo "✅ Real stage 10 still present"
echo "✅ No CI wrapper / no external disk build root"
echo "@@ENDLUME_STAGE|FINAL 8.39 FIX2: запускаю полный build + gates"
echo "@@ENDLUME_PROGRESS|3"
ENDLUME_IN_APP_UPDATE=1 /bin/bash "$PATCHED"
