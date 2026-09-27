#!/bin/bash
set -Eeuo pipefail

ROOT="$HOME/.endlume-github-release-agent"
CHECKOUT="$ROOT/repo"
STATE="$ROOT/last-success.txt"
LOCK="$ROOT/lock"
LOG="$ROOT/agent.log"
REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.cargo/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH HOME COPYFILE_DISABLE=1 COPY_EXTENDED_ATTRIBUTES_DISABLE=1 ENDLUME_IN_APP_UPDATE=1
mkdir -p "$ROOT"
exec >>"$LOG" 2>&1
printf '[%s] poll\n' "$(date '+%Y-%m-%d %H:%M:%S')"

if ! mkdir "$LOCK" 2>/dev/null; then
  # Remove only a stale lock. A live agent keeps it.
  if ! pgrep -f "$ROOT/agent.sh" >/dev/null 2>&1; then
    rmdir "$LOCK" >/dev/null 2>&1 || true
    mkdir "$LOCK" 2>/dev/null || { echo 'stale lock could not be recovered'; exit 0; }
  else
    echo 'build already running'
    exit 0
  fi
fi
cleanup(){ rmdir "$LOCK" >/dev/null 2>&1 || true; }
trap cleanup EXIT

command -v gh >/dev/null 2>&1 || { echo 'gh missing'; exit 0; }
gh auth status -h github.com >/dev/null 2>&1 || { echo 'gh auth unavailable'; exit 0; }

REQ_JSON="$(gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/updates/github/build-request.json?ref=$BRANCH" 2>/dev/null || true)"
[[ -n "$REQ_JSON" ]] || { echo 'request unavailable'; exit 0; }
META="$(python3 -c 'import json,sys,os;r=json.load(sys.stdin);print(("1" if r.get("enabled") else "0")+"\t"+str(r.get("generation",0))+"\t"+str(r.get("version","")).strip()+"\t"+os.path.basename(str(r.get("builder","")).strip()))' <<<"$REQ_JSON")"
IFS=$'\t' read -r ENABLED GENERATION VERSION BUILDER <<<"$META"
[[ "$ENABLED" == 1 && -n "$VERSION" ]] || { echo 'release disabled'; exit 0; }
[[ "$BUILDER" == BUILD_ENDLUME_*.command && "$BUILDER" != *'/'* && "$BUILDER" != *'..'* ]] || { echo "unsafe builder $BUILDER"; exit 1; }
STATE_KEY="$VERSION|$GENERATION"
LAST="$(cat "$STATE" 2>/dev/null || true)"

public_release_valid(){
  local tmp="${TMPDIR:-/tmp}/endlume-agent-latest-$$.json"
  /usr/bin/curl -fsSL --connect-timeout 8 --max-time 20 \
    "https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/latest.json" -o "$tmp" 2>/dev/null || { rm -f "$tmp"; return 1; }
  python3 - "$tmp" "$VERSION" <<'PY' >/dev/null 2>&1
import json,sys
p,v=sys.argv[1:]
d=json.load(open(p)); x=d.get('platforms',{}).get('darwin-aarch64',{})
assert d.get('version')==v
assert x.get('url') and x.get('signature')
PY
  local code=$?
  rm -f "$tmp"
  return "$code"
}

# Never skip solely because state says success: the public updater must also be valid.
if [[ "$STATE_KEY" == "$LAST" ]] && public_release_valid; then
  echo "already published $STATE_KEY"
  exit 0
fi

if [[ ! -d "$CHECKOUT/.git" ]]; then
  rm -rf "$CHECKOUT"
  gh repo clone "$REPO" "$CHECKOUT" -- --branch "$BRANCH" --single-branch
else
  git -C "$CHECKOUT" fetch origin "$BRANCH" --quiet
  git -C "$CHECKOUT" reset --hard "origin/$BRANCH" --quiet
  git -C "$CHECKOUT" clean -fd --quiet
fi

cd "$CHECKOUT"
chmod +x scripts/publish-github-release-macos.sh "$BUILDER"
if /bin/bash scripts/publish-github-release-macos.sh; then
  public_release_valid || { echo "publish returned success but public updater is invalid"; exit 1; }
  printf '%s\n' "$STATE_KEY" > "$STATE"
  echo "published $STATE_KEY"
else
  code=$?
  echo "publish $STATE_KEY failed: $code"
  exit "$code"
fi
