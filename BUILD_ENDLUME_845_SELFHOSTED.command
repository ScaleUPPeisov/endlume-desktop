#!/bin/bash
set -Eeuo pipefail
BASE_DIR="$(cd "$(dirname "$0")" && pwd)";BASE="$BASE_DIR/BUILD_ENDLUME_844_SELFHOSTED.command";TMP="$(mktemp -d /tmp/endlume-845-builder.XXXXXX)";PATCHED="$TMP/BUILD_ENDLUME_845_FROM_844.command"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; };trap cleanup EXIT
fail(){ echo "❌ ENDLUME 8.45 BUILDER: $1" >&2; exit 1; }
[[ -f "$BASE" ]] || fail "8.44 proven builder missing"
python3 - "$BASE" "$PATCHED" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text(encoding='utf-8')
needle='scripts/apply-vyron-bridge-8-44.py scripts/validate-release-8-44.sh'
if s.count(needle)<2: raise SystemExit('8.45 builder: expected 8.44 dependency lists missing')
s=s.replace(needle,needle+' scripts/apply-finalize-hotfix-8-45.py scripts/validate-release-8-45.sh')
needle='    "scripts/validate-release-8-44.sh \\"$FFMPEG\\" \\"$FFPROBE\\"\\n"\n'
if needle not in s: raise SystemExit('8.45 builder: 8.44 runtime validator insertion marker missing')
s=s.replace(needle,needle+'    "python3 scripts/apply-finalize-hotfix-8-45.py\\n"\n    "chmod +x scripts/validate-release-8-45.sh\\n"\n    "scripts/validate-release-8-45.sh \\"$FFMPEG\\" \\"$FFPROBE\\"\\n"\n',1)
old="s=s.replace('1.0.0-alpha.8.41','1.0.0-alpha.8.44')";new="s=s.replace('1.0.0-alpha.8.41','1.0.0-alpha.8.45')"
if old not in s: raise SystemExit('8.45 builder: final identity rewrite marker missing')
s=s.replace(old,new,1)
old="if 'VERSION_EXPECTED=\"1.0.0-alpha.8.44\"' not in s:";new="if 'VERSION_EXPECTED=\"1.0.0-alpha.8.45\"' not in s:"
if old not in s: raise SystemExit('8.45 builder: REAL version assertion missing')
s=s.replace(old,new,1)
old=("    'stage \"7/10 Проверяю ENDLUME 8.44 • VYRON Bridge + полный 8.43 regression\" 58\\n'\n""    'chmod +x scripts/validate-release-8-44.sh\\n'\n""    'scripts/validate-release-8-44.sh \"$FFMPEG\" \"$FFPROBE\"\\n'\n""    'gh api -H \\\'Accept: application/vnd.github.raw+json\\\' \"/repos/$REPO/contents/scripts/validate-motion-ui-8-41.mjs?ref=release\" > scripts/validate-motion-ui-8-41.mjs\\n'\n""    'node scripts/validate-motion-ui-8-41.mjs\\n'\n")
new=("    'stage \"7/10 Проверяю ENDLUME 8.45 • FAST FINALIZE + полный 8.44 regression\" 58\\n'\n""    'chmod +x scripts/validate-release-8-45.sh\\n'\n""    'scripts/validate-release-8-45.sh \"$FFMPEG\" \"$FFPROBE\"\\n'\n""    'gh api -H \\\'Accept: application/vnd.github.raw+json\\\' \"/repos/$REPO/contents/scripts/validate-motion-ui-8-41.mjs?ref=release\" > scripts/validate-motion-ui-8-41.mjs\\n'\n""    'node scripts/validate-motion-ui-8-41.mjs\\n'\n")
if old not in s: raise SystemExit('8.45 builder: final Stage 7 block missing')
s=s.replace(old,new,1)
old="for marker in ('apply-online-updater-8-42.py','apply-real-fps-8-43.py','apply-vyron-bridge-8-44.py','validate-release-8-44.sh'):";new="for marker in ('apply-online-updater-8-42.py','apply-real-fps-8-43.py','apply-vyron-bridge-8-44.py','validate-release-8-44.sh','apply-finalize-hotfix-8-45.py','validate-release-8-45.sh'):"
if old not in s: raise SystemExit('8.45 builder: REAL marker tuple missing')
s=s.replace(old,new,1)
s=s.replace("grep -Fq \\\'VERSION_EXPECTED=\"1.0.0-alpha.8.44\"\\\' \"$REAL\" || fail \"8.44 final version gate missing\"","grep -Fq \\\'VERSION_EXPECTED=\"1.0.0-alpha.8.45\"\\\' \"$REAL\" || fail \"8.45 final version gate missing\"")
needle="    'grep -Fq \\\'validate-release-8-44.sh\\\' \"$REAL\" || fail \"8.44 final validator missing\"\\n'\n"
if needle not in s: raise SystemExit('8.45 builder: CORE 8.44 validator gate missing')
s=s.replace(needle,needle+"    'grep -Fq \\\'apply-finalize-hotfix-8-45.py\\\' \"$REAL\" || fail \"8.45 patch missing\"\\n'\n    'grep -Fq \\\'validate-release-8-45.sh\\\' \"$REAL\" || fail \"8.45 validator missing\"\\n'\n",1)
s=s.replace('✅ ENDLUME 8.44 signed updater artifact ready','✅ ENDLUME 8.45 signed updater artifact ready').replace('✅ ENDLUME 8.44 post-8.43 REAL transformation PASS','✅ ENDLUME 8.45 post-8.44 FINALIZE transformation PASS')
Path(sys.argv[2]).write_text(s,encoding='utf-8')
PY
chmod +x "$PATCHED";/bin/bash -n "$PATCHED" || fail "transformed 8.45 builder syntax failed"
grep -Fq 'apply-finalize-hotfix-8-45.py' "$PATCHED" || fail "8.45 patch wiring missing";grep -Fq 'validate-release-8-45.sh' "$PATCHED" || fail "8.45 validator wiring missing";grep -Fq '1.0.0-alpha.8.45' "$PATCHED" || fail "8.45 identity missing"
echo '✅ ENDLUME 8.45 builder wraps the proven 8.44 chain';echo '✅ 8.44 completes first; 8.45 changes final FFprobe/finalize only';echo '✅ codecs / audio / Effects / Subscribe / VYRON bridge remain inherited'
exec /bin/bash "$PATCHED"
