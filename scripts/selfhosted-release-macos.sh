#!/bin/bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
REQ="updates/cloudflare/build-request.json"
BUCKET="endlume-private-updates"
KEY="$HOME/.endlume-updater/endlume.key"
ART="${RUNNER_TEMP:-/tmp}/endlume-release-${GITHUB_RUN_ID:-local}-mac"
rm -rf "$ART"; mkdir -p "$ART"

readarray -t META < <(python3 - "$REQ" <<'PY'
import json,sys,os
r=json.load(open(sys.argv[1]))
if not r.get('enabled'): raise SystemExit('release request disabled')
b=os.path.basename(r.get('builder',''))
if b!=r.get('builder') or not b.startswith('BUILD_ENDLUME_') or not b.endswith('.command'): raise SystemExit('unsafe builder')
print(r['version']);print(b);print(r.get('notes',''))
PY
)
VERSION="${META[0]}"; BUILDER="${META[1]}"; NOTES="${META[2]:-}"
[[ -f "$BUILDER" ]] || { echo "Builder missing: $BUILDER" >&2; exit 1; }
[[ -s "$KEY" ]] || { echo "Updater signing key missing: $KEY" >&2; exit 1; }
chmod 600 "$KEY" || true

export TAURI_SIGNING_PRIVATE_KEY="$KEY"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD=""
export ENDLUME_RELEASE_ARTIFACT_DIR="$ART"
export ENDLUME_RELEASE_PLATFORM="darwin-aarch64"
export ENDLUME_RELEASE_VERSION="$VERSION"

/bin/bash "$BUILDER"

ASSET="$(find "$ART" -maxdepth 3 -type f -name '*.app.tar.gz' -print -quit)"
[[ -n "$ASSET" && -f "$ASSET" ]] || { echo "No macOS updater .app.tar.gz in $ART" >&2; find "$ART" -maxdepth 3 -type f -print; exit 1; }
SIG_FILE="$ASSET.sig"
[[ -s "$SIG_FILE" ]] || { echo "Missing updater signature: $SIG_FILE" >&2; exit 1; }
SIG="$(cat "$SIG_FILE")"
NAME="$(basename "$ASSET")"
OBJECT_KEY="releases/endlume/stable/darwin-aarch64/$VERSION/$NAME"

npx --yes wrangler@4 r2 object put "$BUCKET/$OBJECT_KEY" --file "$ASSET" --remote

MANIFEST="$ART/darwin-aarch64.json"
python3 - "$MANIFEST" "$VERSION" "$NOTES" "$OBJECT_KEY" "$SIG" <<'PY'
import json,sys,datetime
path,version,notes,key,sig=sys.argv[1:]
with open(path,'w',encoding='utf-8') as f:
  json.dump({'version':version,'notes':notes,'pub_date':datetime.datetime.now(datetime.timezone.utc).isoformat(),'object_key':key,'signature':sig},f,ensure_ascii=False,indent=2)
PY
npx --yes wrangler@4 r2 object put "$BUCKET/manifests/endlume/stable/darwin-aarch64.json" --file "$MANIFEST" --remote

echo "ENDLUME $VERSION macOS signed updater published to private R2"
