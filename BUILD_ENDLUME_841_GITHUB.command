#!/bin/bash
set -Eeuo pipefail
export COPYFILE_DISABLE=1
export COPY_EXTENDED_ATTRIBUTES_DISABLE=1

REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
TMP="$(mktemp -d /tmp/endlume-841-github.XXXXXX)"
BASE="$TMP/BUILD_ENDLUME_840_DRAGDROP_MAC.command"
GEN="$TMP/BUILD_ENDLUME_841_GENERATOR.command"
REAL="$TMP/BUILD_ENDLUME_841_REAL.command"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo; echo "❌ ENDLUME 8.41 ONLINE: $1"; exit 1; }

echo "ENDLUME Studio 1.0.0-alpha.8.41 • SIGNED ONLINE UPDATE"
echo "ONLY requested 1-10 fixes • 8.40 native updater • no manual install"
echo
[[ "$(uname -s)" == Darwin && "$(uname -m)" == arm64 ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"
[[ -n "${ENDLUME_RELEASE_ARTIFACT_DIR:-}" ]] || fail "ENDLUME_RELEASE_ARTIFACT_DIR missing"
[[ -n "${TAURI_SIGNING_PRIVATE_KEY_PATH:-}" ]] || fail "TAURI_SIGNING_PRIVATE_KEY_PATH missing"
[[ -s "$TAURI_SIGNING_PRIVATE_KEY_PATH" ]] || fail "Tauri updater signing key missing"

# All new patches must exist before we generate or build anything.
for path in scripts/apply-performance-stability-8-41.py scripts/apply-version-8-41.py scripts/validate-release-8-41.sh; do
  gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/$path?ref=$BRANCH" > "$TMP/$(basename "$path")" || fail "не удалось получить $path"
  [[ -s "$TMP/$(basename "$path")" ]] || fail "$path пуст"
done
python3 -m py_compile "$TMP/apply-performance-stability-8-41.py" "$TMP/apply-version-8-41.py" || fail "8.41 Python patch syntax failed"
/bin/bash -n "$TMP/validate-release-8-41.sh" || fail "8.41 validator syntax failed"

gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/BUILD_ENDLUME_840_DRAGDROP_MAC.command?ref=$BRANCH" > "$BASE" || fail "не удалось получить proven 8.40 bootstrap builder"
[[ -s "$BASE" ]] || fail "8.40 builder пуст"
/bin/bash -n "$BASE" || fail "8.40 builder syntax failed"

# Turn the proven 8.40 outer builder into GENERATE-ONLY mode. It still runs all
# its structural prechecks, but it does not start npm/cargo/Tauri itself.
python3 - "$BASE" "$GEN" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text(encoding='utf-8')
old='/bin/bash "$REAL"\n'
pos=s.rfind(old)
if pos<0: raise SystemExit('8.41: 8.40 final REAL execution marker missing')
# It must be the final executable action, otherwise we could accidentally build 8.40.
tail=s[pos+len(old):].strip()
if tail: raise SystemExit('8.41: unexpected commands after 8.40 REAL execution marker')
s=s[:pos]+'cp "$REAL" "$ENDLUME_841_GENERATED_BUILDER"\n'
Path(sys.argv[2]).write_text(s,encoding='utf-8')
PY
chmod +x "$GEN"
/bin/bash -n "$GEN" || fail "8.41 generate-only wrapper syntax failed"
export ENDLUME_841_GENERATED_BUILDER="$REAL"
/bin/bash "$GEN"
[[ -s "$REAL" ]] || fail "8.40 proven REAL builder was not generated"
/bin/bash -n "$REAL" || fail "generated REAL builder syntax failed"

# Upgrade the generated 8.40 REAL builder to 8.41. Historical 8.38/8.40 gates
# remain before this patch. After 8.41 migration only the 8.41 final gate runs.
python3 - "$REAL" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text(encoding='utf-8')

# Insert 8.41 immediately after the FIRST executable 8.40 updater gate.
call40='scripts/validate-release-8-40.sh'
needle='\n'+call40+'\n'
i=s.find(needle)
if i<0: raise SystemExit('8.41: executable 8.40 updater gate missing')
insert_at=i+len(needle)
patch='''python3 -m py_compile scripts/apply-performance-stability-8-41.py scripts/apply-version-8-41.py
python3 scripts/apply-performance-stability-8-41.py
python3 scripts/apply-version-8-41.py
chmod +x scripts/validate-release-8-41.sh
scripts/validate-release-8-41.sh "$FFMPEG" "$FFPROBE"
'''
s=s[:insert_at]+patch+s[insert_at:]

# Final identity: all final app gates and user-visible build labels become 8.41.
s=s.replace('VERSION_EXPECTED="1.0.0-alpha.8.40"','VERSION_EXPECTED="1.0.0-alpha.8.41"',1)
s=s.replace('ENDLUME Studio 1.0.0-alpha.8.40','ENDLUME Studio 1.0.0-alpha.8.41')
s=s.replace('│ 8.40 • STABLE 8.38 BASE • NATIVE INTERNET UPDATER        │','│ 8.41 • TRUE 60 FPS • STABILITY • GAPLESS • CHROMA        │')
s=s.replace('[[ "$APP_VERSION" == "1.0.0-alpha.8.40" ]]','[[ "$APP_VERSION" == "1.0.0-alpha.8.41" ]]')

# Stage 7 must no longer run the 8.40 render-baseline (it expects fps:30).
old_stage='''stage "7/10 Проверяю ENDLUME 8.40 final regression" 58
chmod +x scripts/validate-release-8-40.sh scripts/validate-render-baseline-8-40.sh
scripts/validate-release-8-40.sh
scripts/validate-render-baseline-8-40.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs
'''
new_stage='''stage "7/10 Проверяю ENDLUME 8.41 • только пункты 1–10" 58
chmod +x scripts/validate-release-8-41.sh
scripts/validate-release-8-41.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs
'''
if old_stage not in s: raise SystemExit('8.41: expected 8.40 Stage 7 block missing')
s=s.replace(old_stage,new_stage,1)

# Build updater artifacts using the MAIN config. The old local config explicitly
# disables createUpdaterArtifacts and would produce no .app.tar.gz/.sig.
old_build='npx tauri build --target aarch64-apple-darwin --bundles app --config src-tauri/tauri.local.conf.json'
new_build='npx tauri build --target aarch64-apple-darwin --bundles app'
if old_build not in s: raise SystemExit('8.41: Tauri local-config build marker missing')
s=s.replace(old_build,new_build,1)

# Replace drag/drop packaging with signed updater artifact export. Nothing touches
# /Applications here: installed 8.40 receives 8.41 through the native updater.
stage10='stage "10/10 Готовлю файл для папки Программы" 96\n'
j=s.find(stage10)
if j<0: raise SystemExit('8.41: 8.40 dragdrop Stage 10 marker missing')
release=r'''stage "10/10 Экспортирую подписанное ONLINE обновление" 96
OUT="${ENDLUME_RELEASE_ARTIFACT_DIR:?ENDLUME_RELEASE_ARTIFACT_DIR missing}"
mkdir -p "$OUT"
BUNDLE_DIR="src-tauri/target/aarch64-apple-darwin/release/bundle/macos"
UPDATER="$(find "$BUNDLE_DIR" -maxdepth 1 -type f -name '*.app.tar.gz' -print -quit)"
[[ -n "$UPDATER" && -s "$UPDATER" ]] || fail "Tauri updater .app.tar.gz не создан"
[[ -s "$UPDATER.sig" ]] || fail "Tauri updater .sig не создан"
cp "$UPDATER" "$OUT/$(basename "$UPDATER")"
cp "$UPDATER.sig" "$OUT/$(basename "$UPDATER").sig"
[[ -s "$OUT/$(basename "$UPDATER")" && -s "$OUT/$(basename "$UPDATER").sig" ]] || fail "artifact export incomplete"
echo "@@ENDLUME_PROGRESS|100"
echo "✅ ENDLUME 8.41 signed updater artifact ready"
echo "Artifact dir: $OUT"
'''
s=s[:j]+release+'\n'

Path(sys.argv[1]).write_text(s,encoding='utf-8')
PY

/bin/bash -n "$REAL" || fail "8.41 REAL builder syntax failed"

# Mandatory preflight: fail FAST before npm/cargo/FFmpeg if ordering or scope is bad.
python3 - "$REAL" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text(encoding='utf-8')
call38='scripts/validate-release-8-38.sh "$FFMPEG" "$FFPROBE"'
apply40='python3 scripts/apply-github-updater-8-40.py'
ver40='python3 scripts/apply-version-8-40.py'
call40='scripts/validate-release-8-40.sh'
apply41='python3 scripts/apply-performance-stability-8-41.py'
ver41='python3 scripts/apply-version-8-41.py'
call41='scripts/validate-release-8-41.sh "$FFMPEG" "$FFPROBE"'

if s.count(call38)!=1: raise SystemExit(f'PRECHECK 8.41: historical 8.38 validator count={s.count(call38)}')
p38=s.index(call38); p40=s.index(apply40); v40=s.index(ver40)
# Find executable call, not chmod text.
c40=s.find('\n'+call40+'\n',v40)
if not (p38<p40<v40<c40): raise SystemExit('PRECHECK 8.41: 8.38 -> updater40 -> version40 -> validate40 order broken')
p41=s.index(apply41,c40); v41=s.index(ver41,p41); c41=s.find('\n'+call41+'\n',v41)
if not (c40<p41<v41<c41): raise SystemExit('PRECHECK 8.41: validate40 -> patch41 -> version41 -> validate41 order broken')
if call38 in s[v40:]: raise SystemExit('PRECHECK 8.41: 8.38 validator runs after 8.40 migration')
if 'scripts/validate-render-baseline-8-40.sh "$FFMPEG" "$FFPROBE"' in s[c41:]: raise SystemExit('PRECHECK 8.41: fps30 baseline runs after 8.41 migration')
for bad in ['apply-performance-fidelity-8-39.py','repair-render-chroma-8-39.py','apply-hybrid-updater-8-39.py','validate-release-8-39.sh']:
    if bad in s: raise SystemExit(f'PRECHECK 8.41: forbidden 8.39 chain leaked: {bad}')
if 'ENDLUME_Studio_8.40_MAC.zip' in s or 'Готовлю файл для папки Программы' in s:
    raise SystemExit('PRECHECK 8.41: dragdrop packaging survived')
if '--config src-tauri/tauri.local.conf.json' in s:
    raise SystemExit('PRECHECK 8.41: updater artifacts still disabled by local config')
if 'Экспортирую подписанное ONLINE обновление' not in s:
    raise SystemExit('PRECHECK 8.41: signed artifact export missing')
print('✅ PRECHECK 8.41: historical gates ordered correctly')
print('✅ PRECHECK 8.41: 8.39 chain absent')
print('✅ PRECHECK 8.41: 8.41 patch/version/gate ordered correctly')
print('✅ PRECHECK 8.41: signed updater artifacts enabled')
print('✅ PRECHECK 8.41: no /Applications install / dragdrop stage')
PY

grep -Fq 'VERSION_EXPECTED="1.0.0-alpha.8.41"' "$REAL" || fail "8.41 final version gate missing"
grep -Fq 'apply-performance-stability-8-41.py' "$REAL" || fail "8.41 targeted patch missing"
grep -Fq 'validate-release-8-41.sh' "$REAL" || fail "8.41 full gate missing"
grep -Fq 'npx tauri build --target aarch64-apple-darwin --bundles app' "$REAL" || fail "signed Tauri build missing"
grep -Fq 'Экспортирую подписанное ONLINE обновление' "$REAL" || fail "signed artifact stage missing"

echo "✅ ENDLUME 8.41 ONLINE preflight passed"
echo "✅ Only requested 1–10 patch will be applied after proven 8.40 updater bootstrap"
echo "✅ Proven 500k speed/size budget is guarded by validate-release-8-41.sh"
echo "✅ No manual installer will be produced"
/bin/bash "$REAL"
