#!/bin/bash
set -Eeuo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$BASE_DIR/BUILD_ENDLUME_845_SELFHOSTED.command"
TMP="$(mktemp -d /tmp/endlume-846-builder.XXXXXX)"
WRAP="$TMP/BUILD_ENDLUME_846_WRAPPED.command"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo "❌ ENDLUME 8.46 BUILDER: $1" >&2; exit 1; }
[[ -f "$BASE" ]] || fail "8.45 builder missing"
[[ -f "$BASE_DIR/BUILD_ENDLUME_844_SELFHOSTED.command" ]] || fail "8.44 proven builder missing"
[[ -f "$BASE_DIR/BUILD_ENDLUME_841_PINNED.command" ]] || fail "8.41 pinned foundation missing"
cp "$BASE_DIR/BUILD_ENDLUME_844_SELFHOSTED.command" "$TMP/BUILD_ENDLUME_844_SELFHOSTED.command"
cp "$BASE_DIR/BUILD_ENDLUME_841_PINNED.command" "$TMP/BUILD_ENDLUME_841_PINNED.command"
chmod +x "$TMP/BUILD_ENDLUME_844_SELFHOSTED.command" "$TMP/BUILD_ENDLUME_841_PINNED.command"

python3 - "$BASE" "$WRAP" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text(encoding='utf-8')
needle='exec /bin/bash "$PATCHED"\n'
if s.count(needle)!=1: raise SystemExit('8.46 wrapper: 8.45 final exec marker missing/non-unique')
inject=r'''python3 - "$PATCHED" <<'PY846'
from pathlib import Path
import sys
p=Path(sys.argv[1]);s=p.read_text(encoding='utf-8')
needle='    "scripts/validate-release-8-45.sh \\\"$FFMPEG\\\" \\\"$FFPROBE\\\"\\n"\n'
if needle not in s: raise SystemExit('8.46 effective builder: 8.45 runtime gate marker missing')
motion='    "gh api -H \\\'Accept: application/vnd.github.raw+json\\\' \\\"/repos/$REPO/contents/scripts/validate-motion-ui-8-41.mjs?ref=release\\\" > scripts/validate-motion-ui-8-41.mjs || fail \\\"cannot fetch 60 FPS UI validator before 8.45 gate\\\"\\n"\n'
insert=motion+needle+(
'    "mkdir -p scripts\\n"\n'
'    "gh api -H \\\'Accept: application/vnd.github.raw+json\\\' \\\"/repos/$REPO/contents/scripts/apply-render-stability-8-46.py?ref=candidate/render-stability-8.46\\\" > scripts/apply-render-stability-8-46.py || fail \\\"cannot fetch 8.46 migration\\\"\\n"\n'
'    "gh api -H \\\'Accept: application/vnd.github.raw+json\\\' \\\"/repos/$REPO/contents/scripts/validate-release-8-46.sh?ref=candidate/render-stability-8.46\\\" > scripts/validate-release-8-46.sh || fail \\\"cannot fetch 8.46 validator\\\"\\n"\n'
'    "python3 -m py_compile scripts/apply-render-stability-8-46.py\\n"\n'
'    "python3 scripts/apply-render-stability-8-46.py\\n"\n'
'    "chmod +x scripts/validate-release-8-46.sh\\n"\n'
'    "scripts/validate-release-8-46.sh \\\"$FFMPEG\\\" \\\"$FFPROBE\\\"\\n"\n'
)
s=s.replace(needle,insert,1)
old=(
'    \'stage "7/10 Проверяю ENDLUME 8.45 • FAST FINALIZE + полный 8.44 regression" 58\\n\'\n'
'    \'chmod +x scripts/validate-release-8-45.sh\\n\'\n'
'    \'scripts/validate-release-8-45.sh "$FFMPEG" "$FFPROBE"\\n\'\n'
'    \'gh api -H \\\'Accept: application/vnd.github.raw+json\\\' "/repos/$REPO/contents/scripts/validate-motion-ui-8-41.mjs?ref=release" > scripts/validate-motion-ui-8-41.mjs\\n\'\n'
'    \'node scripts/validate-motion-ui-8-41.mjs\\n\'\n'
)
new=(
'    \'stage "7/10 Проверяю ENDLUME 8.46 • RENDER STABILITY + полный 8.45 regression" 58\\n\'\n'
'    \'chmod +x scripts/validate-release-8-46.sh\\n\'\n'
'    \'scripts/validate-release-8-46.sh "$FFMPEG" "$FFPROBE"\\n\'\n'
'    \'node scripts/validate-motion-ui-8-41.mjs\\n\'\n'
)
if old not in s: raise SystemExit('8.46 effective builder: final 8.45 Stage 7 block missing')
s=s.replace(old,new,1)
s=s.replace('1.0.0-alpha.8.45','1.0.0-alpha.8.46')
s=s.replace('✅ ENDLUME 8.45 signed updater artifact ready','✅ ENDLUME 8.46 candidate signed artifact ready')
s=s.replace('✅ ENDLUME 8.45 post-8.44 FINALIZE transformation PASS','✅ ENDLUME 8.46 post-8.45 RENDER STABILITY transformation PASS')
p.write_text(s,encoding='utf-8')
PY846
/bin/bash -n "$PATCHED" || fail "8.46 transformed effective builder syntax failed"
grep -Fq 'apply-render-stability-8-46.py' "$PATCHED" || fail "8.46 migration wiring missing"
grep -Fq 'validate-release-8-46.sh' "$PATCHED" || fail "8.46 validator wiring missing"
grep -Fq 'validate-motion-ui-8-41.mjs' "$PATCHED" || fail "motion validator prefetch missing"
grep -Fq '1.0.0-alpha.8.46' "$PATCHED" || fail "8.46 identity wiring missing"
echo '✅ 8.46 candidate wraps proven 8.45 builder'
echo '✅ 8.45 final FFprobe gate has its required motion validator before execution'
echo '✅ 8.46 stability migration runs only after 8.45 passes'
exec /bin/bash "$PATCHED"
'''
s=s.replace(needle,inject,1)
Path(sys.argv[2]).write_text(s,encoding='utf-8')
PY
chmod +x "$WRAP"
/bin/bash -n "$WRAP" || fail "wrapper syntax failed"
grep -Fq 'PY846' "$WRAP" || fail "effective-tree transform missing"
exec /bin/bash "$WRAP"
