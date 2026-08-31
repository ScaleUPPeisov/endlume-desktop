#!/bin/bash
set -Eeuo pipefail

REPO="ScaleUPPeisov/endlume-desktop"
REAL_GH="/opt/homebrew/bin/gh"
BASE="$(cd "$(dirname "$0")" && pwd)"

[[ -x "$REAL_GH" ]] || { echo 'gh binary missing' >&2; exit 1; }
[[ -n "${GH_TOKEN:-}" ]] || { echo 'GH_TOKEN missing in self-hosted job' >&2; exit 1; }

gh(){
  if [[ "${1:-}" == "auth" && "${2:-}" == "status" ]]; then
    "$REAL_GH" api "/repos/$REPO" --jq .full_name >/dev/null
    return $?
  fi

  local joined=" $* "
  if [[ "$joined" == *'/contents/BUILD_ENDLUME_841_GITHUB.command?ref=release'* ]]; then
    "$REAL_GH" "$@" | python3 -c 'import sys
s=sys.stdin.read()
# Keep the 8.41 queue-aware motion gate used by the proven 8.41 path.
old="node scripts/validate-motion-ui.mjs"
new="gh api -H '\''Accept: application/vnd.github.raw+json'\'' \"/repos/$REPO/contents/scripts/validate-motion-ui-8-41.mjs?ref=release\" > scripts/validate-motion-ui-8-41.mjs\\nnode scripts/validate-motion-ui-8-41.mjs"
i=s.rfind(old)
assert i>=0,"8.42 bridge: 8.41 motion marker missing"
s=s[:i]+new+s[i+len(old):]
# Add updater-only 8.42 migration immediately after the executable 8.41 gate.
needle="scripts/validate-release-8-41.sh \"$FFMPEG\" \"$FFPROBE\"\\n"
insert=(needle+
"for path in scripts/apply-online-updater-8-42.py scripts/apply-version-8-42.py scripts/validate-release-8-42.sh; do\\n"
"  gh api -H '\''Accept: application/vnd.github.raw+json'\'' \"/repos/$REPO/contents/$path?ref=release\" > \"$path\" || fail \"cannot fetch $path\"\\n"
"  [[ -s \"$path\" ]] || fail \"$path empty\"\\n"
"done\\n"
"python3 -m py_compile scripts/apply-online-updater-8-42.py scripts/apply-version-8-42.py\\n"
"python3 scripts/apply-online-updater-8-42.py\\n"
"python3 scripts/apply-version-8-42.py\\n"
"chmod +x scripts/validate-release-8-42.sh\\n"
"scripts/validate-release-8-42.sh\\n")
assert needle in s,"8.42 bridge: executable 8.41 gate missing"
s=s.replace(needle,insert,1)
# Final identity becomes 8.42 while preserving all 8.41 render patches.
s=s.replace("1.0.0-alpha.8.41","1.0.0-alpha.8.42")
s=s.replace("7/10 Проверяю ENDLUME 8.41 • только пункты 1–10","7/10 Проверяю ENDLUME 8.42 • Online Update System validation")
# The final Stage 7 gate must validate 8.42, not rerun only 8.41.
stage="chmod +x scripts/validate-release-8-41.sh\\nscripts/validate-release-8-41.sh \"$FFMPEG\" \"$FFPROBE\"\\ngh api -H '\''Accept: application/vnd.github.raw+json'\'' \"/repos/$REPO/contents/scripts/validate-motion-ui-8-41.mjs?ref=release\" > scripts/validate-motion-ui-8-41.mjs\\nnode scripts/validate-motion-ui-8-41.mjs"
replacement="chmod +x scripts/validate-release-8-42.sh\\nscripts/validate-release-8-42.sh\\ngh api -H '\''Accept: application/vnd.github.raw+json'\'' \"/repos/$REPO/contents/scripts/validate-motion-ui-8-41.mjs?ref=release\" > scripts/validate-motion-ui-8-41.mjs\\nnode scripts/validate-motion-ui-8-41.mjs"
if stage in s: s=s.replace(stage,replacement,1)
s=s.replace("✅ ENDLUME 8.41 signed updater artifact ready","✅ ENDLUME 8.42 signed updater artifact ready")
sys.stdout.write(s)'
    return ${PIPESTATUS[0]}
  fi

  "$REAL_GH" "$@"
}
export -f gh
export REAL_GH REPO

"$REAL_GH" api "/repos/$REPO" --jq .full_name >/dev/null || { echo 'GitHub Actions token cannot read ENDLUME repository' >&2; exit 1; }

for path in scripts/apply-online-updater-8-42.py scripts/apply-version-8-42.py scripts/validate-release-8-42.sh; do
  "$REAL_GH" api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/$path?ref=release" > "/tmp/$(basename "$path")"
done
python3 -m py_compile /tmp/apply-online-updater-8-42.py /tmp/apply-version-8-42.py
/bin/bash -n /tmp/validate-release-8-42.sh

echo '✅ ENDLUME 8.42 updater-only bridge active'
echo '✅ Proven 8.41 render path preserved'
echo '✅ Native updater migration/gate will run after 8.41 gate'

chmod +x "$BASE/BUILD_ENDLUME_841_PINNED.command"
exec /bin/bash "$BASE/BUILD_ENDLUME_841_PINNED.command"
