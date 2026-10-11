#!/bin/bash
set -Eeuo pipefail
: "${ROLLBACK_DIR:?ROLLBACK_DIR missing}"
: "${GH_TOKEN:?GH_TOKEN missing}"
STABLE_REPO='ScaleUPPeisov/scaleup-site'
STABLE_TAG='endlume-stable'
OLD_MANIFEST="$ROLLBACK_DIR/latest-10.0.12.json"
OLD_TAR="$ROLLBACK_DIR/ENDLUME-macos-aarch64-10.0.12.app.tar.gz"
OLD_SIG="$ROLLBACK_DIR/ENDLUME-macos-aarch64-10.0.12.app.tar.gz.sig"
for f in "$OLD_MANIFEST" "$OLD_TAR" "$OLD_SIG"; do test -s "$f"; done
python3 - "$OLD_MANIFEST" <<'PY'
import json,sys
m=json.load(open(sys.argv[1])); assert m['version']=='10.0.12',m.get('version')
PY
TMP="$(mktemp -d)"
cp "$OLD_TAR" "$TMP/ENDLUME-macos-aarch64.app.tar.gz"
cp "$OLD_SIG" "$TMP/ENDLUME-macos-aarch64.app.tar.gz.sig"
cp "$OLD_MANIFEST" "$TMP/latest.json"
# Generic package/signature first, manifest last, mirroring forward publication order.
gh release upload "$STABLE_TAG" "$TMP/ENDLUME-macos-aarch64.app.tar.gz" "$TMP/ENDLUME-macos-aarch64.app.tar.gz.sig" --clobber --repo "$STABLE_REPO"
gh release upload "$STABLE_TAG" "$TMP/latest.json" --clobber --repo "$STABLE_REPO"
BASE="https://github.com/$STABLE_REPO/releases/download/$STABLE_TAG"
sleep 2
curl -fL --retry 5 "$BASE/latest.json?rollback=$(date +%s)" -o "$TMP/check.json"
python3 - "$TMP/check.json" <<'PY'
import json,sys
m=json.load(open(sys.argv[1])); assert m['version']=='10.0.12',m.get('version')
print('GITHUB_STABLE_ROLLBACK_TO_10_0_12=PASS')
PY
