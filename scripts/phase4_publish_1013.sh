#!/bin/bash
set -Eeuo pipefail

: "${PHASE4_ARTIFACT_DIR:?PHASE4_ARTIFACT_DIR missing}"
: "${ROLLBACK_DIR:?ROLLBACK_DIR missing}"
: "${GH_TOKEN:?GH_TOKEN missing}"
STABLE_REPO='ScaleUPPeisov/scaleup-site'
STABLE_TAG='endlume-stable'
BASE_URL="https://github.com/$STABLE_REPO/releases/download/$STABLE_TAG"
SRC="$PHASE4_ARTIFACT_DIR"

RELEASE_JSON="$(find "$SRC" -type f -name 'ENDLUME-10.0.13-release.json' -print -quit)"
LATEST="$(find "$SRC" -type f -name 'latest.json' -print -quit)"
ZIP="$(find "$SRC" -type f -name 'ENDLUME-10.0.13-macos-aarch64.app.zip' -print -quit)"
VTAR="$(find "$SRC" -type f -name 'ENDLUME-10.0.13-macos-aarch64.app.tar.gz' -print -quit)"
VSIG="$(find "$SRC" -type f -name 'ENDLUME-10.0.13-macos-aarch64.app.tar.gz.sig' -print -quit)"
GTAR="$(find "$SRC" -type f -name 'ENDLUME-macos-aarch64.app.tar.gz' -print -quit)"
GSIG="$(find "$SRC" -type f -name 'ENDLUME-macos-aarch64.app.tar.gz.sig' -print -quit)"
SUMS="$(find "$SRC" -type f -name 'SHA256SUMS.txt' -print -quit)"
for f in "$RELEASE_JSON" "$LATEST" "$ZIP" "$VTAR" "$VSIG" "$GTAR" "$GSIG" "$SUMS"; do test -s "$f"; done

python3 - "$RELEASE_JSON" "$LATEST" "$GTAR" "$GSIG" <<'PY'
import hashlib,json,sys
release,latest,tar,sig=sys.argv[1:]
r=json.load(open(release)); m=json.load(open(latest))
assert r['releaseStatus']=='PREFLIGHT_PASS'
assert r['releaseVersion']=='10.0.13'
assert r['sourceEngineHead']=='e4a07972b1566ed73b11c4eb758d59f4dc839e71'
assert r['functionalProductDiff']==0
for k in ['fastEngineFunctionalDiff','projectUiFunctionalDiff','effectsFunctionalDiff','subscribeFunctionalDiff','previewFunctionalDiff','renderCenterFunctionalDiff','iconDiff']:
    assert r[k]==0,(k,r[k])
assert r['signatureVerify']=='PASS'
assert r['latestJsonSha256Field']=='PASS'
assert r['updaterKeyId']=='00351d4950cd22d3'
assert r['updaterPubkeySha256']=='c320c0fbea2d494349f780cee70267d97eab9d4a0bde5e8721a0c9acb18548d6'
p=m['platforms']['darwin-aarch64']
assert m['version']=='10.0.13'
assert p['url'].endswith('/ENDLUME-macos-aarch64.app.tar.gz')
assert p.get('signature')
assert p.get('sha256')
tarsha=hashlib.sha256(open(tar,'rb').read()).hexdigest()
sigsha=hashlib.sha256(open(sig,'rb').read()).hexdigest()
assert tarsha==p['sha256']==r['tarGzSha256'],(tarsha,p['sha256'],r['tarGzSha256'])
assert sigsha==r['signatureSha256'],(sigsha,r['signatureSha256'])
print('PUBLISH_INPUT_PREFLIGHT=PASS')
print('TAR_GZ_SHA256='+tarsha)
print('SIGNATURE_SHA256='+sigsha)
PY

mkdir -p "$ROLLBACK_DIR"
# Preserve exact live 10.0.12 updater state before any mutation.
curl -fL --retry 5 "$BASE_URL/latest.json?rollback=$(date +%s)" -o "$ROLLBACK_DIR/latest-10.0.12.json"
curl -fL --retry 5 "$BASE_URL/ENDLUME-macos-aarch64.app.tar.gz?rollback=$(date +%s)" -o "$ROLLBACK_DIR/ENDLUME-macos-aarch64-10.0.12.app.tar.gz"
curl -fL --retry 5 "$BASE_URL/ENDLUME-macos-aarch64.app.tar.gz.sig?rollback=$(date +%s)" -o "$ROLLBACK_DIR/ENDLUME-macos-aarch64-10.0.12.app.tar.gz.sig"
python3 - "$ROLLBACK_DIR/latest-10.0.12.json" <<'PY'
import json,sys
m=json.load(open(sys.argv[1])); assert m['version']=='10.0.12',m.get('version')
print('ROLLBACK_MANIFEST_VERSION=10.0.12')
PY
/usr/bin/shasum -a 256 "$ROLLBACK_DIR"/* > "$ROLLBACK_DIR/SHA256SUMS-10.0.12.txt"
cat > "$ROLLBACK_DIR/ROLLBACK.md" <<'EOF'
ENDLUME 10.0.12 live updater rollback snapshot captured before 10.0.13 publication.
Do not delete 10.0.12 versioned release assets.
EOF

gh release view "$STABLE_TAG" --repo "$STABLE_REPO" >/dev/null
# Publish immutable/versioned 10.0.13 assets first.
gh release upload "$STABLE_TAG" "$ZIP" "$VTAR" "$VSIG" "$RELEASE_JSON" "$SUMS" --clobber --repo "$STABLE_REPO"
# Switch generic package/signature only after versioned assets exist.
gh release upload "$STABLE_TAG" "$GTAR" "$GSIG" --clobber --repo "$STABLE_REPO"

# Verify public package before flipping manifest.
TMP="$(mktemp -d)"
curl -fL --retry 5 "$BASE_URL/ENDLUME-macos-aarch64.app.tar.gz?verify=$(date +%s)" -o "$TMP/live.tar.gz"
LIVE_SHA="$(/usr/bin/shasum -a 256 "$TMP/live.tar.gz" | awk '{print $1}')"
EXPECTED_SHA="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["platforms"]["darwin-aarch64"]["sha256"])' "$LATEST")"
test "$LIVE_SHA" = "$EXPECTED_SHA"
echo PUBLIC_PACKAGE_SHA256="$LIVE_SHA"

# Manifest is intentionally published last.
gh release upload "$STABLE_TAG" "$LATEST" --clobber --repo "$STABLE_REPO"
sleep 2
curl -fL --retry 5 "$BASE_URL/latest.json?verify=$(date +%s)" -o "$TMP/latest.json"
python3 - "$TMP/latest.json" "$EXPECTED_SHA" <<'PY'
import json,sys
m=json.load(open(sys.argv[1])); sha=sys.argv[2]
assert m['version']=='10.0.13',m.get('version')
p=m['platforms']['darwin-aarch64']
assert p['sha256']==sha
assert p['signature']
assert p['url']=='https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/ENDLUME-macos-aarch64.app.tar.gz'
print('LIVE_GITHUB_MANIFEST_10_0_13=PASS')
print('LATEST_JSON_SHA256_FIELD=PASS')
PY

echo STABLE_GITHUB_PUBLISH=PASS
