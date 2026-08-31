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

chmod +x "$BASE/BUILD_ENDLUME_841_PINNED.command"
exec /bin/bash "$BASE/BUILD_ENDLUME_841_PINNED.command"
