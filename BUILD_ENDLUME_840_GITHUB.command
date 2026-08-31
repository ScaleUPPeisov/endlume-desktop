#!/bin/bash
set -Eeuo pipefail

REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
TMP="$(mktemp -d /tmp/endlume-840-github.XXXXXX)"
GEN="$TMP/BUILD_ENDLUME_839_LOCAL.command"
GEN840="$TMP/BUILD_ENDLUME_840_GENERATOR.command"
REAL="$TMP/BUILD_ENDLUME_840_REAL.command"
REPAIR="$TMP/repair-render-chroma-8-39.py"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo; echo "❌ ENDLUME 8.40 GITHUB: $1"; exit 1; }

echo "ENDLUME Studio 1.0.0-alpha.8.40 • SIGNED GITHUB UPDATER"
echo "8.39 fidelity/performance preserved • native Tauri updater • artifact-only release"
echo
[[ "$(uname -s)" == Darwin && "$(uname -m)" == arm64 ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"
[[ -n "${ENDLUME_RELEASE_ARTIFACT_DIR:-}" ]] || fail "ENDLUME_RELEASE_ARTIFACT_DIR missing"
[[ -n "${TAURI_SIGNING_PRIVATE_KEY_PATH:-}" ]] || fail "TAURI_SIGNING_PRIVATE_KEY_PATH missing"
[[ -s "$TAURI_SIGNING_PRIVATE_KEY_PATH" ]] || fail "Tauri private signing key missing"

gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/BUILD_ENDLUME_839_LOCAL.command?ref=$BRANCH" > "$GEN" || fail "не удалось получить proven 8.39 generator"
gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/scripts/repair-render-chroma-8-39.py?ref=$BRANCH" > "$REPAIR" || fail "не удалось получить structural chroma repair"
[[ -s "$GEN" && -s "$REPAIR" ]] || fail "8.39 generator/chroma repair пуст"
/bin/bash -n "$GEN" || fail "8.39 generator syntax failed"
python3 -m py_compile "$REPAIR" || fail "structural chroma repair syntax failed"
grep -Fq "if 'chromakey=' in line and 'color_ffmpeg(&e.key_color)' in line:" "$REPAIR" || fail "old brittle chroma repair returned"
grep -Fq 'despill=type={}:mix={}:expand=0.20' "$REPAIR" || fail "chroma repair despill normalization missing"

python3 - "$GEN" "$GEN840" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text(encoding='utf-8')

# Generate only; the outer 8.40 builder will execute the real builder after
# replacing Stage 10 install with artifact export.
last='/bin/bash "$PATCHED"\n'
if last not in s: raise SystemExit('8.40: generator final execution marker missing')
s=s.replace(last,'cp "$PATCHED" "$ENDLUME_840_GENERATED_BUILDER"\n',1)

# Final build identity.
s=s.replace('1.0.0-alpha.8.39','1.0.0-alpha.8.40')
s=s.replace('endlume-desktop-8.39','endlume-desktop-8.40')
s=s.replace('│ 8.39 • TRUE 60 FPS • STABILITY • AUDIO • CHROMA          │','│ 8.40 • NATIVE SIGNED UPDATER • 8.39 FIDELITY PRESERVED   │')

# Stage 7 must validate the new updater, not the historical hybrid updater.
old='''stage "7/10 Проверяю 60 FPS / UI / Crossfade / Chroma / Speed-Size" 58
chmod +x scripts/validate-release-8-39.sh
scripts/validate-release-8-39.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs
'''
new='''stage "7/10 Проверяю Native Updater / UI / release wiring" 58
chmod +x scripts/validate-release-8-40.sh
scripts/validate-release-8-40.sh
node scripts/validate-motion-ui.mjs
'''
if old not in s: raise SystemExit('8.40: stage7 8.39 marker missing')
s=s.replace(old,new,1)

# Preserve the full 8.39 gate BEFORE replacing the hybrid updater with native.
# IMPORTANT: the structural chroma normalizer MUST run before the 8.39 patch.
# This is the exact regression that previously stopped 8.39/8.40 at stage 6.
needle='''python3 scripts/apply-performance-fidelity-8-39.py
python3 scripts/apply-hybrid-updater-8-39.py
python3 scripts/apply-version-8-39.py
'''
add='''python3 -m py_compile scripts/repair-render-chroma-8-39.py
python3 scripts/repair-render-chroma-8-39.py
python3 scripts/apply-performance-fidelity-8-39.py
python3 scripts/apply-hybrid-updater-8-39.py
python3 scripts/apply-version-8-39.py
chmod +x scripts/validate-release-8-39.sh
scripts/validate-release-8-39.sh "$FFMPEG" "$FFPROBE"
python3 -m py_compile scripts/apply-github-updater-8-40.py scripts/apply-version-8-40.py
python3 scripts/apply-github-updater-8-40.py
python3 scripts/apply-version-8-40.py
chmod +x scripts/validate-release-8-40.sh
scripts/validate-release-8-40.sh
'''
if needle not in s: raise SystemExit('8.40: 8.39 policy tail missing')
s=s.replace(needle,add,1)

# Require the repaired path in the generated builder.
req="        'validate-release-8-39.sh',\n"
if req in s:
    s=s.replace(req,req+"        'repair-render-chroma-8-39.py',\n        'apply-github-updater-8-40.py',\n        'validate-release-8-40.sh',\n",1)

Path(sys.argv[2]).write_text(s,encoding='utf-8')
PY

chmod +x "$GEN840"
/bin/bash -n "$GEN840" || fail "8.40 generator syntax failed"
export ENDLUME_840_GENERATED_BUILDER="$REAL"
/bin/bash "$GEN840"
[[ -s "$REAL" ]] || fail "8.40 real builder was not generated"
/bin/bash -n "$REAL" || fail "generated 8.40 builder syntax failed"

python3 - "$REAL" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text(encoding='utf-8')
repair='python3 scripts/repair-render-chroma-8-39.py'
perf='python3 scripts/apply-performance-fidelity-8-39.py'
ri=s.find(repair); pi=s.find(perf)
if ri < 0: raise SystemExit('8.40: structural chroma repair missing from real builder')
if pi < 0: raise SystemExit('8.40: performance patch missing from real builder')
if ri > pi: raise SystemExit('8.40: chroma repair runs AFTER performance patch')
marker='stage "10/10 Устанавливаю обновление" 96\n'
i=s.find(marker)
if i<0: raise SystemExit('8.40: real stage10 marker missing')
release=r'''stage "10/10 Экспортирую подписанный updater artifact" 96
OUT="${ENDLUME_RELEASE_ARTIFACT_DIR:?ENDLUME_RELEASE_ARTIFACT_DIR missing}"
mkdir -p "$OUT"
BUNDLE_DIR="src-tauri/target/aarch64-apple-darwin/release/bundle/macos"
UPDATER="$(find "$BUNDLE_DIR" -maxdepth 1 -type f -name '*.app.tar.gz' -print -quit)"
[[ -n "$UPDATER" && -f "$UPDATER" ]] || fail "Tauri updater .app.tar.gz не создан"
[[ -s "$UPDATER.sig" ]] || fail "Tauri updater signature не создан"
cp "$UPDATER" "$OUT/$(basename "$UPDATER")"
cp "$UPDATER.sig" "$OUT/$(basename "$UPDATER").sig"
[[ -s "$OUT/$(basename "$UPDATER")" && -s "$OUT/$(basename "$UPDATER").sig" ]] || fail "artifact export incomplete"
echo "@@ENDLUME_PROGRESS|100"
echo "✅ ENDLUME 8.40 signed updater artifact ready"
echo "Artifact dir: $OUT"
'''
s=s[:i]+release+'\n'
p.write_text(s,encoding='utf-8')
PY

/bin/bash -n "$REAL" || fail "artifact-mode builder syntax failed"
grep -Fq 'VERSION_EXPECTED="1.0.0-alpha.8.40"' "$REAL" || fail "8.40 version gate missing"
grep -Fq 'python3 scripts/repair-render-chroma-8-39.py' "$REAL" || fail "structural chroma repair missing"
grep -Fq 'apply-github-updater-8-40.py' "$REAL" || fail "native updater patch missing"
grep -Fq 'validate-release-8-40.sh' "$REAL" || fail "8.40 gate missing"
grep -Fq 'Экспортирую подписанный updater artifact' "$REAL" || fail "artifact-only stage10 missing"
if grep -Fq 'Atomic swap' "$REAL"; then fail "manual application install survived in release builder"; fi
REPAIR_LINE="$(grep -nF 'python3 scripts/repair-render-chroma-8-39.py' "$REAL" | head -1 | cut -d: -f1)"
PERF_LINE="$(grep -nF 'python3 scripts/apply-performance-fidelity-8-39.py' "$REAL" | head -1 | cut -d: -f1)"
[[ "$REPAIR_LINE" =~ ^[0-9]+$ && "$PERF_LINE" =~ ^[0-9]+$ && "$REPAIR_LINE" -lt "$PERF_LINE" ]] || fail "chroma repair execution order invalid"

echo "✅ 8.40 preflight passed"
echo "✅ Repeated failure blocked: structural chroma repair runs BEFORE 8.39 performance patch"
echo "✅ Full 8.39 fidelity gate runs before updater migration"
echo "✅ Native updater gate wired"
echo "✅ Stage 10 exports signed artifact; /Applications is not touched"
ENDLUME_IN_APP_UPDATE=1 /bin/bash "$REAL"
