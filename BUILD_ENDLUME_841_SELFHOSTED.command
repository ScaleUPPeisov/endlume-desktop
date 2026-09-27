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

  # ENDLUME 8.40 historical motion gate must stay byte-for-byte intact so the
  # 8.41 transformer can recognize it. Replace ONLY the final/last motion gate,
  # which belongs to the generated 8.41 Stage 7.
  local joined=" $* "
  if [[ "$joined" == *'/contents/BUILD_ENDLUME_841_GITHUB.command?ref=release'* ]]; then
    "$REAL_GH" "$@" | python3 -c 'import sys; s=sys.stdin.read(); old="node scripts/validate-motion-ui.mjs"; new="gh api -H '\''Accept: application/vnd.github.raw+json'\'' \"/repos/$REPO/contents/scripts/validate-motion-ui-8-41.mjs?ref=release\" > scripts/validate-motion-ui-8-41.mjs\\nnode scripts/validate-motion-ui-8-41.mjs"; i=s.rfind(old); assert i>=0, "8.41 motion validator marker missing"; sys.stdout.write(s[:i]+new+s[i+len(old):])'
    return ${PIPESTATUS[0]}
  fi

  "$REAL_GH" "$@"
}
export -f gh
export REAL_GH REPO

"$REAL_GH" api "/repos/$REPO" --jq .full_name >/dev/null || {
  echo 'GitHub Actions token cannot read ENDLUME repository' >&2
  exit 1
}

echo '✅ SELF-HOSTED GitHub token bridge active'
echo '✅ Legacy gh auth status checks mapped to repository access check'
echo '✅ ENDLUME 8.41 queue-aware motion validator bridge active (final Stage 7 only)'

chmod +x "$BASE/BUILD_ENDLUME_841_PINNED.command"
exec /bin/bash "$BASE/BUILD_ENDLUME_841_PINNED.command"
