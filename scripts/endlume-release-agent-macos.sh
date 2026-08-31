#!/bin/bash
set -Eeuo pipefail

REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
ROOT="$HOME/.endlume-release-agent"
CHECKOUT="$ROOT/repo"
STATE="$ROOT/last-success.txt"
LOCK="$ROOT/lock"
LOG="$ROOT/agent.log"
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH HOME
mkdir -p "$ROOT"

exec >>"$LOG" 2>&1

echo "[$(/bin/date '+%Y-%m-%d %H:%M:%S')] poll"

# Atomic mkdir lock: if a previous build is still running, do nothing.
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "build already running"
  exit 0
fi
cleanup(){ rmdir "$LOCK" >/dev/null 2>&1 || true; }
trap cleanup EXIT

command -v gh >/dev/null 2>&1 || { echo "gh missing"; exit 0; }
gh auth status -h github.com >/dev/null 2>&1 || { echo "gh auth unavailable"; exit 0; }

REQ_JSON="$(gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/updates/cloudflare/build-request.json?ref=$BRANCH" 2>/dev/null || true)"
[[ -n "$REQ_JSON" ]] || { echo "build request unavailable"; exit 0; }

META="$(python3 -c 'import json,sys,os; r=json.load(sys.stdin); v=str(r.get("version","")).strip(); b=os.path.basename(str(r.get("builder","")).strip()); e=bool(r.get("enabled")); print(("1" if e else "0")+"\t"+v+"\t"+b)' <<<"$REQ_JSON")"
IFS=$'\t' read -r ENABLED VERSION BUILDER <<<"$META"
[[ "$ENABLED" == "1" && -n "$VERSION" ]] || { echo "release request disabled/empty"; exit 0; }
[[ "$BUILDER" == BUILD_ENDLUME_*.command && "$BUILDER" != *'/'* && "$BUILDER" != *'..'* ]] || { echo "unsafe builder: $BUILDER"; exit 1; }
LAST="$(cat "$STATE" 2>/dev/null || true)"
[[ "$VERSION" != "$LAST" ]] || { echo "already published $VERSION"; exit 0; }

if [[ ! -d "$CHECKOUT/.git" ]]; then
  rm -rf "$CHECKOUT"
  gh repo clone "$REPO" "$CHECKOUT" -- --branch "$BRANCH" --single-branch
else
  git -C "$CHECKOUT" fetch origin "$BRANCH" --quiet
  git -C "$CHECKOUT" reset --hard "origin/$BRANCH" --quiet
  git -C "$CHECKOUT" clean -fd --quiet
fi

cd "$CHECKOUT"
[[ -f "$BUILDER" ]] || { echo "builder missing after sync: $BUILDER"; exit 1; }
[[ -f scripts/selfhosted-release-macos.sh ]] || { echo "publisher missing"; exit 1; }
chmod +x "$BUILDER" scripts/selfhosted-release-macos.sh

# The publisher reads build-request.json and performs build/sign/upload.
if /bin/bash scripts/selfhosted-release-macos.sh; then
  printf '%s\n' "$VERSION" > "$STATE"
  echo "published $VERSION successfully"
else
  code=$?
  echo "publish $VERSION failed with code $code"
  exit "$code"
fi
