#!/bin/bash
set -Eeuo pipefail
ROOT="$HOME/.endlume-release-agent-vps"
CHECKOUT="$ROOT/repo"
STATE="$ROOT/last-success.txt"
LOCK="$ROOT/lock"
LOG="$ROOT/agent.log"
REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH HOME
mkdir -p "$ROOT"
exec >>"$LOG" 2>&1
printf '[%s] poll\n' "$(date '+%Y-%m-%d %H:%M:%S')"
if ! mkdir "$LOCK" 2>/dev/null; then echo 'build already running'; exit 0; fi
cleanup(){ rmdir "$LOCK" >/dev/null 2>&1 || true; }
trap cleanup EXIT
command -v gh >/dev/null 2>&1 || { echo 'gh missing'; exit 0; }
gh auth status -h github.com >/dev/null 2>&1 || { echo 'gh auth unavailable'; exit 0; }
REQ_JSON="$(gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/updates/vps/build-request.json?ref=$BRANCH" 2>/dev/null || true)"
[[ -n "$REQ_JSON" ]] || { echo 'request unavailable'; exit 0; }
META="$(python3 -c 'import json,sys,os;r=json.load(sys.stdin);print(("1" if r.get("enabled") else "0")+"\t"+str(r.get("version","")).strip()+"\t"+os.path.basename(str(r.get("builder","")).strip()))' <<<"$REQ_JSON")"
IFS=$'\t' read -r ENABLED VERSION BUILDER <<<"$META"
[[ "$ENABLED" == 1 && -n "$VERSION" ]] || { echo 'release disabled'; exit 0; }
[[ "$BUILDER" == BUILD_ENDLUME_*.command && "$BUILDER" != *'/'* && "$BUILDER" != *'..'* ]] || { echo "unsafe builder $BUILDER"; exit 1; }
LAST="$(cat "$STATE" 2>/dev/null || true)"
[[ "$VERSION" != "$LAST" ]] || { echo "already published $VERSION"; exit 0; }
if [[ ! -d "$CHECKOUT/.git" ]]; then
  rm -rf "$CHECKOUT"; gh repo clone "$REPO" "$CHECKOUT" -- --branch "$BRANCH" --single-branch
else
  git -C "$CHECKOUT" fetch origin "$BRANCH" --quiet
  git -C "$CHECKOUT" reset --hard "origin/$BRANCH" --quiet
  git -C "$CHECKOUT" clean -fd --quiet
fi
cd "$CHECKOUT"
chmod +x scripts/publish-vps-release-macos.sh "$BUILDER"
if /bin/bash scripts/publish-vps-release-macos.sh; then
  printf '%s\n' "$VERSION" > "$STATE"
  echo "published $VERSION"
else
  code=$?; echo "publish $VERSION failed: $code"; exit "$code"
fi
