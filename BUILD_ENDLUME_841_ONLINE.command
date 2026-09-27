#!/bin/bash
set -Eeuo pipefail

# LaunchAgents start with a minimal PATH. Make the online release independent of
# Terminal shell profiles so Homebrew Node/gh and rustup/cargo are always found.
PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.cargo/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH HOME COPYFILE_DISABLE=1 COPY_EXTENDED_ATTRIBUTES_DISABLE=1

REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
DIAG_PATH="updates/github/last-failure.txt"
RUN_LOG="${TMPDIR:-/tmp}/endlume-841-online-last.log"

publish_failure_diag(){
  local code="$1"
  local diag="${TMPDIR:-/tmp}/endlume-841-failure.txt"
  {
    echo "ENDLUME 8.41 ONLINE BUILD FAILURE"
    echo "exit_code=$code"
    echo "time=$(date '+%Y-%m-%d %H:%M:%S %z')"
    echo "builder=BUILD_ENDLUME_841_ONLINE.command"
    echo "---- last 220 lines ----"
    tail -n 220 "$RUN_LOG" 2>/dev/null || true
  } > "$diag"
  # Redact the user home path; never include signing-key contents.
  python3 - "$diag" "$HOME" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); home=sys.argv[2]
s=p.read_text(encoding='utf-8',errors='replace').replace(home,'~')
p.write_text(s,encoding='utf-8')
PY
  local encoded sha
  encoded="$(/usr/bin/base64 < "$diag" | tr -d '\r\n')"
  sha="$(gh api "/repos/$REPO/contents/$DIAG_PATH?ref=$BRANCH" --jq '.sha' 2>/dev/null || true)"
  if [[ -n "$sha" ]]; then
    gh api --method PUT "/repos/$REPO/contents/$DIAG_PATH" \
      -f message="Record ENDLUME 8.41 automatic build failure" \
      -f branch="$BRANCH" -f sha="$sha" -f content="$encoded" >/dev/null 2>&1 || true
  else
    gh api --method PUT "/repos/$REPO/contents/$DIAG_PATH" \
      -f message="Record ENDLUME 8.41 automatic build failure" \
      -f branch="$BRANCH" -f content="$encoded" >/dev/null 2>&1 || true
  fi
}

# Publisher provides the private signing-key path. Tauri CLI 2.10+ accepts
# TAURI_SIGNING_PRIVATE_KEY_PATH; also expose the standard key variable as the
# same local path for maximum build/bundler compatibility. The key stays local.
[[ -n "${TAURI_SIGNING_PRIVATE_KEY_PATH:-}" ]] || { echo '8.41 online: signing key path missing' >&2; exit 1; }
[[ -s "$TAURI_SIGNING_PRIVATE_KEY_PATH" ]] || { echo '8.41 online: signing key file missing' >&2; exit 1; }
export TAURI_SIGNING_PRIVATE_KEY="$TAURI_SIGNING_PRIVATE_KEY_PATH"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="${TAURI_SIGNING_PRIVATE_KEY_PASSWORD:-}"

command -v gh >/dev/null 2>&1 || { echo '8.41 online: gh missing' >&2; exit 1; }
command -v node >/dev/null 2>&1 || { echo '8.41 online: node missing' >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo '8.41 online: npm missing' >&2; exit 1; }
command -v npx >/dev/null 2>&1 || { echo '8.41 online: npx missing' >&2; exit 1; }
command -v cargo >/dev/null 2>&1 || { echo '8.41 online: cargo missing' >&2; exit 1; }
command -v rustup >/dev/null 2>&1 || { echo '8.41 online: rustup missing' >&2; exit 1; }

[[ -x /bin/bash ]] || exit 1
[[ -f BUILD_ENDLUME_841_GITHUB.command ]] || { echo '8.41 online: core builder missing' >&2; exit 1; }
/bin/bash -n BUILD_ENDLUME_841_GITHUB.command

echo "✅ 8.41 LaunchAgent toolchain + signing environment ready"
rm -f "$RUN_LOG"
set +e
/bin/bash BUILD_ENDLUME_841_GITHUB.command 2>&1 | tee "$RUN_LOG"
code=${PIPESTATUS[0]}
set -e
if [[ "$code" -ne 0 ]]; then
  publish_failure_diag "$code"
  echo "❌ ENDLUME 8.41 online build failed; diagnostics uploaded to $DIAG_PATH" >&2
  exit "$code"
fi

# Clear previous diagnostic after a successful build.
sha="$(gh api "/repos/$REPO/contents/$DIAG_PATH?ref=$BRANCH" --jq '.sha' 2>/dev/null || true)"
if [[ -n "$sha" ]]; then
  gh api --method DELETE "/repos/$REPO/contents/$DIAG_PATH" \
    -f message="Clear ENDLUME 8.41 build failure after success" \
    -f branch="$BRANCH" -f sha="$sha" >/dev/null 2>&1 || true
fi

echo "✅ ENDLUME 8.41 online builder completed"
