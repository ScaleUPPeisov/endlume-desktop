#!/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
REQ="updates/vps/build-request.json"
CFG="$HOME/.endlume-updater/vps.env"
KEY="$HOME/.endlume-updater/endlume.key"
SSH_KEY="$HOME/.endlume-updater/vps_deploy_ed25519"
ART="${TMPDIR:-/tmp}/endlume-vps-release-${RANDOM}-mac"
rm -rf "$ART"; mkdir -p "$ART"

[[ -s "$CFG" ]] || { echo "VPS updater config missing: $CFG" >&2; exit 1; }
set -a; source "$CFG"; set +a
: "${ENDLUME_VPS_HOST:?}" "${ENDLUME_VPS_USER:?}" "${ENDLUME_VPS_PORT:?}" "${ENDLUME_UPDATE_BASE_URL:?}"

python3 - "$REQ" <<'PY'
import json,sys,os
r=json.load(open(sys.argv[1]))
if not r.get('enabled'): raise SystemExit('release request disabled')
b=os.path.basename(r.get('builder',''))
if b!=r.get('builder') or not b.startswith('BUILD_ENDLUME_') or not b.endswith('.command'): raise SystemExit('unsafe builder')
PY
VERSION="$(python3 -c 'import json;print(json.load(open("updates/vps/build-request.json"))["version"])')"
BUILDER="$(python3 -c 'import json;print(json.load(open("updates/vps/build-request.json"))["builder"])')"
NOTES="$(python3 -c 'import json;print(json.load(open("updates/vps/build-request.json")).get("notes",""))')"

[[ -f "$BUILDER" ]] || { echo "Builder missing: $BUILDER" >&2; exit 1; }
[[ -s "$KEY" ]] || { echo "Tauri signing key missing: $KEY" >&2; exit 1; }
[[ -s "$SSH_KEY" ]] || { echo "VPS SSH key missing: $SSH_KEY" >&2; exit 1; }

export TAURI_SIGNING_PRIVATE_KEY="$KEY"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD=""
export ENDLUME_RELEASE_ARTIFACT_DIR="$ART"
export ENDLUME_RELEASE_PLATFORM="darwin-aarch64"
export ENDLUME_RELEASE_VERSION="$VERSION"
/bin/bash "$BUILDER"

ASSET="$(find "$ART" -maxdepth 5 -type f -name '*.app.tar.gz' -print -quit)"
[[ -n "$ASSET" && -f "$ASSET" ]] || { echo "No macOS updater artifact in $ART" >&2; find "$ART" -type f -print; exit 1; }
SIG_FILE="$ASSET.sig"; [[ -s "$SIG_FILE" ]] || { echo "Signature missing: $SIG_FILE" >&2; exit 1; }
SIG="$(tr -d '\r\n' < "$SIG_FILE")"; NAME="$(basename "$ASSET")"
OBJECT_KEY="releases/endlume/stable/darwin-aarch64/$VERSION/$NAME"
MANIFEST="$ART/darwin-aarch64.json"
python3 - "$MANIFEST" "$VERSION" "$NOTES" "$OBJECT_KEY" "$SIG" <<'PY'
import json,sys,datetime
path,version,notes,key,sig=sys.argv[1:]
json.dump({'version':version,'notes':notes,'pub_date':datetime.datetime.now(datetime.timezone.utc).isoformat(),'object_key':key,'signature':sig},open(path,'w'),ensure_ascii=False,indent=2)
PY

SSH=(ssh -i "$SSH_KEY" -p "$ENDLUME_VPS_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$ENDLUME_VPS_USER@$ENDLUME_VPS_HOST")
SCP=(scp -i "$SSH_KEY" -P "$ENDLUME_VPS_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
REMOTE_TMP="/tmp/endlume-publish-${VERSION//[^A-Za-z0-9._-]/_}-$$"
"${SSH[@]}" "mkdir -p '$REMOTE_TMP'"
"${SCP[@]}" "$ASSET" "$MANIFEST" "$ENDLUME_VPS_USER@$ENDLUME_VPS_HOST:$REMOTE_TMP/"
"${SSH[@]}" "set -e; install -d '/var/lib/endlume-updates/$(dirname "$OBJECT_KEY")' '/var/lib/endlume-updates/manifests/endlume/stable'; install -m 0644 '$REMOTE_TMP/$NAME' '/var/lib/endlume-updates/$OBJECT_KEY'; install -m 0644 '$REMOTE_TMP/darwin-aarch64.json' '/var/lib/endlume-updates/manifests/endlume/stable/darwin-aarch64.json'; rm -rf '$REMOTE_TMP'"

curl -fsS "$ENDLUME_UPDATE_BASE_URL/health" >/dev/null
STATUS="$(curl -sS -o /dev/null -w '%{http_code}' "$ENDLUME_UPDATE_BASE_URL/v1/update/darwin/aarch64/0.0.0")"
[[ "$STATUS" == "200" ]] || { echo "Update endpoint returned HTTP $STATUS" >&2; exit 1; }
echo "ENDLUME $VERSION macOS published to $ENDLUME_UPDATE_BASE_URL"
