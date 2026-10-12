#!/bin/bash
set -Eeuo pipefail

: "${PHASE4_ARTIFACT_DIR:?PHASE4_ARTIFACT_DIR missing}"
: "${ROLLBACK_DIR:?ROLLBACK_DIR missing}"
: "${GH_TOKEN:?GH_TOKEN missing}"
STABLE_REPO='ScaleUPPeisov/scaleup-site'
STABLE_TAG='endlume-stable'
BASE_URL="https://github.com/$STABLE_REPO/releases/download/$STABLE_TAG"
SRC="$PHASE4_ARTIFACT_DIR"

RELEASE_JSON="$(find "$SRC" -type f -name 'ENDLUME-10.0.14-release.json' -print -quit)"
ZIP="$(find "$SRC" -type f -name 'ENDLUME-10.0.14-macos-aarch64.app.zip' -print -quit)"
VTAR="$(find "$SRC" -type f -name 'ENDLUME-10.0.14-macos-aarch64.app.tar.gz' -print -quit)"
VSIG="$(find "$SRC" -type f -name 'ENDLUME-10.0.14-macos-aarch64.app.tar.gz.sig' -print -quit)"
GTAR="$(find "$SRC" -type f -name 'ENDLUME-macos-aarch64.app.tar.gz' -print -quit)"
GSIG="$(find "$SRC" -type f -name 'ENDLUME-macos-aarch64.app.tar.gz.sig' -print -quit)"
SUMS="$(find "$SRC" -type f -name 'SHA256SUMS.txt' -print -quit)"
for f in "$RELEASE_JSON" "$ZIP" "$VTAR" "$VSIG" "$GTAR" "$GSIG" "$SUMS"; do test -s "$f"; done

python3 - "$RELEASE_JSON" "$GTAR" "$GSIG" <<'PY'
import hashlib,json,sys
release,tar,sig=sys.argv[1:]
r=json.load(open(release))
assert r['releaseStatus']=='PREPUBLISH_PHYSICAL_PASS',r
assert r['releaseVersion']=='10.0.14',r
assert r['functionalSourceHead']=='55372b94a35ef76ee160347783cf8c62e003fa4e',r
assert r['functionalProductDiff']==0,r
assert r['signatureVerify']=='PASS',r
assert r['packagedSmoke']=='PASS',r
for k in ['vyron','effectsPreview','subscribePreview','realRender']:
    assert r[k]=='PASS',(k,r.get(k))
tarsha=hashlib.sha256(open(tar,'rb').read()).hexdigest()
sigsha=hashlib.sha256(open(sig,'rb').read()).hexdigest()
assert tarsha==r['tarGzSha256'],(tarsha,r['tarGzSha256'])
assert sigsha==r['signatureSha256'],(sigsha,r['signatureSha256'])
print('PUBLISH_INPUT_PREFLIGHT=PASS')
print('TAR_GZ_SHA256='+tarsha)
print('SIGNATURE_SHA256='+sigsha)
PY

mkdir -p "$ROLLBACK_DIR"
CACHE="$(date +%s)-${GITHUB_RUN_ID:-local}"

# Preserve the exact live pre-release updater channel, even if historical
# metadata is stale. This is forensic evidence of what was actually public.
curl -fL --retry 5 "$BASE_URL/latest.json?rollback=$CACHE" -o "$ROLLBACK_DIR/pre-release-live-latest.json"
curl -fL --retry 5 "$BASE_URL/ENDLUME-macos-aarch64.app.tar.gz?rollback=$CACHE" -o "$ROLLBACK_DIR/pre-release-live-generic.tar.gz"
curl -fL --retry 5 "$BASE_URL/ENDLUME-macos-aarch64.app.tar.gz.sig?rollback=$CACHE" -o "$ROLLBACK_DIR/pre-release-live-generic.tar.gz.sig"

# Preserve the immutable/versioned 10.0.13 package, signature and metadata.
# These are the authoritative known-good 10.0.13 rollback bytes.
curl -fL --retry 5 "$BASE_URL/ENDLUME-10.0.13-macos-aarch64.app.tar.gz?rollback=$CACHE" -o "$ROLLBACK_DIR/ENDLUME-10.0.13-macos-aarch64.app.tar.gz"
curl -fL --retry 5 "$BASE_URL/ENDLUME-10.0.13-macos-aarch64.app.tar.gz.sig?rollback=$CACHE" -o "$ROLLBACK_DIR/ENDLUME-10.0.13-macos-aarch64.app.tar.gz.sig"
curl -fL --retry 5 "$BASE_URL/ENDLUME-10.0.13-release.json?rollback=$CACHE" -o "$ROLLBACK_DIR/ENDLUME-10.0.13-release.json"
gh api "repos/$STABLE_REPO/releases/tags/$STABLE_TAG" > "$ROLLBACK_DIR/release-metadata.json"

EXPECTED_1013_SHA='ea47135ecd827e9f65dea64ba5c7524d36733ad9f0749dbd773919a9b7870534'
EXPECTED_1013_SIG_SHA='d2968b4bd6c50081842f7a95cc3190d69f7fe28975e4c17cb35ade378d72dd12'
ACTUAL_1013_SHA="$(/usr/bin/sha256sum "$ROLLBACK_DIR/ENDLUME-10.0.13-macos-aarch64.app.tar.gz" | awk '{print $1}')"
ACTUAL_1013_SIG_SHA="$(/usr/bin/sha256sum "$ROLLBACK_DIR/ENDLUME-10.0.13-macos-aarch64.app.tar.gz.sig" | awk '{print $1}')"
test "$ACTUAL_1013_SHA" = "$EXPECTED_1013_SHA"
test "$ACTUAL_1013_SIG_SHA" = "$EXPECTED_1013_SIG_SHA"

# Build a deterministic rollback channel for 10.0.13 from the preserved
# versioned package/signature. The live manifest was discovered to be stale
# (10.0.12) even though 10.0.13 versioned assets exist; we preserve that stale
# manifest above but rollback must restore the owner's intended stable 10.0.13.
cp "$ROLLBACK_DIR/ENDLUME-10.0.13-macos-aarch64.app.tar.gz" "$ROLLBACK_DIR/ENDLUME-macos-aarch64.app.tar.gz"
cp "$ROLLBACK_DIR/ENDLUME-10.0.13-macos-aarch64.app.tar.gz.sig" "$ROLLBACK_DIR/ENDLUME-macos-aarch64.app.tar.gz.sig"
ROLLBACK_SIG="$(tr -d '\r\n' < "$ROLLBACK_DIR/ENDLUME-macos-aarch64.app.tar.gz.sig")"
python3 - "$ROLLBACK_DIR/pre-release-live-latest.json" "$ROLLBACK_DIR/latest.json" "$ROLLBACK_SIG" "$ACTUAL_1013_SHA" <<'PY'
import json,sys
old,out,sig,sha=sys.argv[1:]
m=json.load(open(old))
pre=m.get('version')
if pre not in ('10.0.12','10.0.13'):
    raise AssertionError(('unexpected pre-release live version',pre))
platforms=m.get('platforms',{})
if 'darwin-aarch64' not in platforms:
    raise AssertionError(platforms.keys())
m['version']='10.0.13'
m['notes']='ENDLUME 10.0.13 rollback channel reconstructed from preserved versioned production assets.'
p=platforms['darwin-aarch64']
p['url']='https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/ENDLUME-macos-aarch64.app.tar.gz'
p['signature']=sig
p['sha256']=sha
m['platforms']={'darwin-aarch64':p}
json.dump(m,open(out,'w'),ensure_ascii=False,indent=2)
print('PRE_RELEASE_LIVE_VERSION='+str(pre))
PY

python3 - "$ROLLBACK_DIR/latest.json" "$ROLLBACK_DIR/ENDLUME-macos-aarch64.app.tar.gz" "$ROLLBACK_DIR/ENDLUME-macos-aarch64.app.tar.gz.sig" <<'PY'
import hashlib,json,sys
latest,tar,sig=sys.argv[1:]
m=json.load(open(latest)); assert m['version']=='10.0.13',m.get('version')
assert set(m.get('platforms',{}))=={'darwin-aarch64'},m.get('platforms',{}).keys()
p=m['platforms']['darwin-aarch64']
tarsha=hashlib.sha256(open(tar,'rb').read()).hexdigest()
sigtxt=open(sig).read().strip()
assert p.get('sha256')==tarsha,(p.get('sha256'),tarsha)
assert p.get('signature')==sigtxt,(len(p.get('signature','')),len(sigtxt))
assert p.get('url')=='https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/ENDLUME-macos-aarch64.app.tar.gz',p.get('url')
print('ROLLBACK_MANIFEST_VERSION=10.0.13')
print('ROLLBACK_GENERIC_SHA256='+tarsha)
print('ROLLBACK_SIGNATURE_TEXT=PASS')
PY

/usr/bin/sha256sum "$ROLLBACK_DIR"/*.json "$ROLLBACK_DIR"/*.tar.gz "$ROLLBACK_DIR"/*.sig > "$ROLLBACK_DIR/SHA256SUMS-ROLLBACK.txt"
cat > "$ROLLBACK_DIR/ROLLBACK.md" <<EOF
ENDLUME 10.0.14 pre-release rollback evidence.

Exact live pre-release updater channel is preserved as:
- pre-release-live-latest.json
- pre-release-live-generic.tar.gz
- pre-release-live-generic.tar.gz.sig

Historical discovery: the live latest.json reported 10.0.12 even though immutable 10.0.13 versioned assets were already present.

Owner-intended rollback target is reconstructed and verified as ENDLUME 10.0.13 using:
- ENDLUME-10.0.13-macos-aarch64.app.tar.gz
- ENDLUME-10.0.13-macos-aarch64.app.tar.gz.sig
- latest.json (10.0.13)
- canonical ENDLUME-macos-aarch64.app.tar.gz/.sig copies

10.0.13 tar SHA256: $ACTUAL_1013_SHA
Restore order: canonical updater tar.gz, canonical .sig, latest.json LAST.
EOF

echo ROLLBACK_EVIDENCE_CAPTURED=PASS

NEW_SHA="$(/usr/bin/sha256sum "$GTAR" | awk '{print $1}')"
NEW_SIG="$(tr -d '\r\n' < "$GSIG")"
LATEST_NEW="$SRC/latest.json"
python3 - "$ROLLBACK_DIR/latest.json" "$LATEST_NEW" "$NEW_SIG" "$NEW_SHA" <<'PY'
import datetime,json,sys
old,out,sig,sha=sys.argv[1:]
m=json.load(open(old))
assert m['version']=='10.0.13'
assert set(m.get('platforms',{}))=={'darwin-aarch64'}
m['version']='10.0.14'
m['notes']='ENDLUME 10.0.14 — physically accepted VYRON routing, Effects Preview, Subscribe Preview/final and production render.'
m['pub_date']=datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')
p=m['platforms']['darwin-aarch64']
p['url']='https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/ENDLUME-macos-aarch64.app.tar.gz'
p['signature']=sig
p['sha256']=sha
json.dump(m,open(out,'w'),ensure_ascii=False,indent=2)
PY

MUTATED=0
rollback_on_error(){
  rc=$?
  if [ "$MUTATED" = 1 ]; then
    echo "PUBLISH_FAILURE_ROLLBACK=START rc=$rc" >&2
    gh release upload "$STABLE_TAG" "$ROLLBACK_DIR/ENDLUME-macos-aarch64.app.tar.gz" "$ROLLBACK_DIR/ENDLUME-macos-aarch64.app.tar.gz.sig" --clobber --repo "$STABLE_REPO" || true
    gh release upload "$STABLE_TAG" "$ROLLBACK_DIR/latest.json" --clobber --repo "$STABLE_REPO" || true
    echo PUBLISH_FAILURE_ROLLBACK=RESTORED_10_0_13 >&2
  fi
  exit "$rc"
}
trap rollback_on_error ERR

gh release view "$STABLE_TAG" --repo "$STABLE_REPO" >/dev/null

# 1) Immutable/versioned 10.0.14 assets first.
gh release upload "$STABLE_TAG" "$ZIP" "$VTAR" "$VSIG" "$RELEASE_JSON" "$SUMS" --clobber --repo "$STABLE_REPO"
TMP="$(mktemp -d)"
for name in ENDLUME-10.0.14-macos-aarch64.app.tar.gz ENDLUME-10.0.14-macos-aarch64.app.tar.gz.sig ENDLUME-10.0.14-release.json; do
  curl -fL --retry 5 "$BASE_URL/$name?verify=$CACHE" -o "$TMP/$name"
  test -s "$TMP/$name"
done
test "$(/usr/bin/sha256sum "$TMP/ENDLUME-10.0.14-macos-aarch64.app.tar.gz" | awk '{print $1}')" = "$NEW_SHA"
cmp -s "$TMP/ENDLUME-10.0.14-macos-aarch64.app.tar.gz.sig" "$VSIG"
echo VERSIONED_10_0_14_PUBLIC=PASS

# 2) Canonical package/signature. From this point any error restores 10.0.13.
MUTATED=1
gh release upload "$STABLE_TAG" "$GTAR" "$GSIG" --clobber --repo "$STABLE_REPO"
curl -fL --retry 5 "$BASE_URL/ENDLUME-macos-aarch64.app.tar.gz?verify=$CACHE-2" -o "$TMP/live.tar.gz"
curl -fL --retry 5 "$BASE_URL/ENDLUME-macos-aarch64.app.tar.gz.sig?verify=$CACHE-2" -o "$TMP/live.sig"
LIVE_SHA="$(/usr/bin/sha256sum "$TMP/live.tar.gz" | awk '{print $1}')"
test "$LIVE_SHA" = "$NEW_SHA"
cmp -s "$TMP/live.sig" "$GSIG"
echo CANONICAL_10_0_14_PACKAGE_PUBLIC=PASS

# 3) latest.json is intentionally switched LAST.
gh release upload "$STABLE_TAG" "$LATEST_NEW" --clobber --repo "$STABLE_REPO"
sleep 2
curl -fL --retry 5 "$BASE_URL/latest.json?verify=$CACHE-3" -o "$TMP/live-latest.json"
python3 - "$TMP/live-latest.json" "$NEW_SHA" "$NEW_SIG" <<'PY'
import json,sys
m=json.load(open(sys.argv[1])); sha=sys.argv[2]; sig=sys.argv[3]
assert m['version']=='10.0.14',m.get('version')
p=m['platforms']['darwin-aarch64']
assert p['sha256']==sha,(p.get('sha256'),sha)
assert p['signature']==sig
assert p['url']=='https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/ENDLUME-macos-aarch64.app.tar.gz'
print('LIVE_LATEST_VERSION=10.0.14')
print('LIVE_LATEST_SIGNATURE=PASS')
print('LIVE_LATEST_SHA256='+sha)
PY
cp "$TMP/live-latest.json" "$SRC/live-latest.json"
printf '%s\n' "$LIVE_SHA" > "$SRC/LIVE_ARTIFACT_SHA256.txt"
MUTATED=0
trap - ERR

echo STABLE_GITHUB_PUBLISH=PASS
echo LIVE_ARTIFACT_SHA256="$LIVE_SHA"
