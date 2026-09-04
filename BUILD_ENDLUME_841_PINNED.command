#!/bin/bash
set -Eeuo pipefail

REPO="ScaleUPPeisov/endlume-desktop"
SOURCE_REF="4bfb9ff9d07c1d67c61e85641805b28c58ab2faa"
TMP="$(mktemp -d /tmp/endlume-841-retry.XXXXXX)"
LEGACY="$TMP/BUILD_ENDLUME_841_PINNED.legacy.command"
PATCHED="$TMP/BUILD_ENDLUME_841_PINNED.retry.command"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo; echo "❌ ENDLUME 8.41 PINNED RETRY: $1" >&2; exit 1; }

export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.cargo/bin:/usr/bin:/bin:/usr/sbin:/sbin"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI missing"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI not authenticated"

fetch_raw_retry(){
  local path="$1" out="$2" tmp="${2}.tmp" attempt
  for attempt in 1 2 3 4 5; do
    rm -f "$tmp"
    if gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/$path?ref=$SOURCE_REF" > "$tmp" && [[ -s "$tmp" ]]; then
      mv "$tmp" "$out"
      return 0
    fi
    rm -f "$tmp"
    echo "⚠️ pinned bootstrap fetch retry $attempt/5: $path" >&2
    sleep $((attempt*2))
  done
  return 1
}

fetch_raw_retry "BUILD_ENDLUME_841_PINNED.command" "$LEGACY" || fail "cannot fetch proven pinned 8.41 builder"
/bin/bash -n "$LEGACY" || fail "proven pinned 8.41 builder syntax failed"

python3 - "$LEGACY" "$PATCHED" <<'PY'
from pathlib import Path
import sys
src,out=sys.argv[1:]
s=Path(src).read_text(encoding='utf-8')
old='''gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/BUILD_ENDLUME_841_GITHUB.command?ref=release" > "$CORE" || fail "cannot fetch 8.41 core builder"'''
new='''core_fetch_ok=0
for attempt in 1 2 3 4 5; do
  rm -f "$CORE"
  if gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/BUILD_ENDLUME_841_GITHUB.command?ref=release" > "$CORE" && [[ -s "$CORE" ]]; then
    core_fetch_ok=1
    break
  fi
  rm -f "$CORE"
  echo "⚠️ 8.41 core builder fetch retry $attempt/5" >&2
  sleep $((attempt*2))
done
[[ "$core_fetch_ok" == 1 ]] || fail "cannot fetch 8.41 core builder after 5 attempts"'''
if old not in s:
    raise SystemExit('retry patch anchor missing')
s=s.replace(old,new,1)
Path(out).write_text(s,encoding='utf-8')
PY

chmod +x "$PATCHED"
/bin/bash -n "$PATCHED" || fail "retry-patched 8.41 builder syntax failed"
grep -Fq '8.41 core builder fetch retry' "$PATCHED" || fail "retry wiring missing"
echo "✅ ENDLUME 8.41 bootstrap network retry hardened"
echo "✅ proven builder source preserved at $SOURCE_REF"
/bin/bash "$PATCHED"
