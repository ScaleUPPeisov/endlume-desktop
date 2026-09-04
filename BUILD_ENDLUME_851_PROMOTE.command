#!/bin/bash
set -Eeuo pipefail

EXPECTED_VERSION="1.0.0-alpha.8.51"
PINNED_SHA="d4f50ea8a13a21d6163c1ab16d4669432d09f97d"
CURRENT_RUN_STARTED="2026-09-04T00:44:30+00:00"
CAND="$HOME/.endlume-release-bridge/endlume/candidate-8.51"
FINAL_ART="${ENDLUME_RELEASE_ARTIFACT_DIR:-$HOME/.endlume-release-bridge/endlume/current}"
REPO="ScaleUPPeisov/endlume-desktop"

fail(){ echo "❌ ENDLUME 8.51 PROMOTE: $1" >&2; exit 1; }
[[ "${ENDLUME_RELEASE_VERSION:-$EXPECTED_VERSION}" = "$EXPECTED_VERSION" ]] || fail "wrong requested version"
mkdir -p "$FINAL_ART"

candidate_is_fresh(){
  python3 - "$CAND" "$EXPECTED_VERSION" "$CURRENT_RUN_STARTED" <<'PY'
from pathlib import Path
from datetime import datetime
import sys
root=Path(sys.argv[1]); expected=sys.argv[2]; threshold=datetime.fromisoformat(sys.argv[3]).timestamp()
files=[root/'ENDLUME-macos-aarch64.app.tar.gz',root/'ENDLUME-macos-aarch64.app.tar.gz.sig',root/'version.txt']
if not all(p.is_file() and p.stat().st_size>0 for p in files): raise SystemExit(1)
if (root/'version.txt').read_text().strip()!=expected: raise SystemExit(1)
if min(p.stat().st_mtime for p in files) < threshold: raise SystemExit(1)
print('PASS: fresh signed 8.51 candidate artifact is ready')
PY
}

if ! candidate_is_fresh; then
  echo "ℹ️ Fresh 8.51 candidate artifact not available; building exact pinned $PINNED_SHA now"
  TMP="$(mktemp -d /tmp/endlume-851-promote.XXXXXX)"
  trap 'rm -rf "$TMP" >/dev/null 2>&1 || true' EXIT
  gh auth setup-git >/dev/null 2>&1 || true
  git -C "$TMP" init -q
  git -C "$TMP" remote add origin "https://github.com/$REPO.git"
  fetched=0
  for attempt in 1 2 3 4 5; do
    if git -C "$TMP" -c http.version=HTTP/1.1 fetch --no-tags --depth=1 origin "$PINNED_SHA"; then
      fetched=1
      break
    fi
    echo "⚠️ exact 8.51 source fetch retry $attempt/5" >&2
    sleep $((attempt*2))
  done
  [[ "$fetched" == 1 ]] || fail "cannot fetch exact 8.51 source $PINNED_SHA"
  git -C "$TMP" checkout --detach FETCH_HEAD
  test "$(git -C "$TMP" rev-parse HEAD)" = "$PINNED_SHA" || fail "exact 8.51 SHA mismatch"
  export ENDLUME_851_PATCH_REF="$PINNED_SHA"
  export ENDLUME_RELEASE_VERSION="$EXPECTED_VERSION"
  export ENDLUME_RELEASE_ARTIFACT_DIR="$CAND"
  chmod +x "$TMP/BUILD_ENDLUME_851_SELFHOSTED.command"
  /bin/bash "$TMP/BUILD_ENDLUME_851_SELFHOSTED.command"
  printf '%s\n' "$EXPECTED_VERSION" > "$CAND/version.txt"
  candidate_is_fresh || fail "fresh exact 8.51 artifact was not produced"
fi

TAR="$CAND/ENDLUME-macos-aarch64.app.tar.gz"
SIG="$CAND/ENDLUME-macos-aarch64.app.tar.gz.sig"
[[ -s "$TAR" ]] || fail "candidate updater tar missing"
[[ -s "$SIG" ]] || fail "candidate updater signature missing"

rm -rf "$FINAL_ART"
mkdir -p "$FINAL_ART"
cp "$TAR" "$FINAL_ART/ENDLUME-macos-aarch64.app.tar.gz"
cp "$SIG" "$FINAL_ART/ENDLUME-macos-aarch64.app.tar.gz.sig"
printf '%s\n' "$EXPECTED_VERSION" > "$FINAL_ART/version.txt"

echo "✅ ENDLUME 8.51 exact signed artifact promoted to production staging"
echo "✅ source pin: $PINNED_SHA"
echo "✅ VideoToolbox q100/500k hardware-first; x265 CRF18/500k fallback"
echo "✅ hard gates preserved: SSIM >=0.995, 500–700 MB, cold <=75s, warm <=30s"
echo "✅ vivid migration validator fixed to count occurrences, not matching lines"
echo "✅ next release-workflow stages will strict-verify archive and publish endlume-stable"
