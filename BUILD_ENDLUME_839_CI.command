#!/bin/bash
set -Eeuo pipefail
REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
TMP_ROOT="$(mktemp -d /tmp/endlume-839-ci.XXXXXX)"
BASE="$TMP_ROOT/BUILD_ENDLUME_836_LOCAL.command"
PATCHED="$TMP_ROOT/BUILD_ENDLUME_839_REAL.command"
cleanup(){ rm -rf "$TMP_ROOT" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo; echo "❌ ENDLUME 8.39 CI: $1"; exit 1; }

echo "ENDLUME Studio 1.0.0-alpha.8.39 • REMOTE CI"
echo "60 FPS • UI stability • crossfade/no-gap • chroma despill • 8.38 speed/size lock"
[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon macOS runner"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"

gh api "repos/$REPO/contents/BUILD_ENDLUME_836_LOCAL.command?ref=$BRANCH" --jq .content | tr -d '\n' | /usr/bin/base64 -D > "$BASE" || fail "не удалось получить canonical 8.36 base builder"
[[ -s "$BASE" ]] || fail "8.36 base builder пуст"

python3 - "$BASE" "$PATCHED" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')

src=src.replace('VERSION_EXPECTED="1.0.0-alpha.8.36"','VERSION_EXPECTED="1.0.0-alpha.8.39"')
src=src.replace('echo "❌ ENDLUME 8.36 остановлена ДО замены приложения"','echo "❌ ENDLUME 8.39 остановлена ДО замены приложения"')
src=src.replace('│ 8.36 • 1080p Fidelity Lock • clean first frame            │','│ 8.39 • TRUE 60 FPS • STABILITY • AUDIO • CHROMA          │')

# CI and local fallback must never select /Volumes/* automatically.
needle="src=src.replace('SRC=\"$WORK_ROOT/endlume-desktop-8.33\"','SRC=\"$WORK_ROOT/endlume-desktop-8.36\"',1)\n"
if needle not in src: raise SystemExit('8.39 CI: work-root transform marker missing')
internal="src=src.replace('WORK_ROOT=\"$(choose_work_root)\"','WORK_ROOT=\"$HOME/.endlume-local-builder\"',1)\n"
src=src.replace(needle,needle+internal,1)

# Validate each established contract before moving to the next release policy.
apply_marker='python3 scripts/apply-version-8-36.py\n'
addition='''chmod +x scripts/validate-release-8-36.sh
scripts/validate-release-8-36.sh "$FFMPEG" "$FFPROBE"
python3 -m py_compile scripts/repair-settings-updater-8-37.py scripts/apply-remote-updater-8-37.py scripts/apply-version-8-37.py scripts/apply-youtube-fill-8-38.py scripts/apply-version-8-38.py scripts/apply-performance-fidelity-8-39.py scripts/apply-version-8-39.py
python3 scripts/repair-settings-updater-8-37.py
python3 scripts/apply-remote-updater-8-37.py
python3 scripts/apply-version-8-37.py
chmod +x scripts/validate-release-8-37.sh
scripts/validate-release-8-37.sh
python3 scripts/apply-youtube-fill-8-38.py
python3 scripts/apply-version-8-38.py
chmod +x scripts/validate-release-8-38.sh
scripts/validate-release-8-38.sh "$FFMPEG" "$FFPROBE"
python3 scripts/apply-performance-fidelity-8-39.py
python3 scripts/apply-version-8-39.py
'''
if apply_marker not in src: raise SystemExit('8.39 CI: apply-version-8-36 marker missing')
src=src.replace(apply_marker,apply_marker+addition,1)

# Replace base stage-7 by the final targeted 8.39 regression gate.
old_stage='''stage "7/10 Гоняю финальный 1080p Fidelity / Audio / Effects regression" 58
chmod +x scripts/validate-release-8-36.sh
scripts/validate-release-8-36.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs
'''
new_stage='''stage "7/10 Проверяю 60 FPS / UI / Crossfade / Chroma / Speed-Size regression" 58
chmod +x scripts/validate-release-8-39.sh
scripts/validate-release-8-39.sh "$FFMPEG" "$FFPROBE"
node scripts/validate-motion-ui.mjs
'''
if old_stage not in src: raise SystemExit('8.39 CI: final stage marker missing')
src=src.replace(old_stage,new_stage,1)

# After the fully-built .app passes its own smoke, package instead of installing
# when running on GitHub Actions. Local install path remains a fallback only.
stage10='stage "10/10 Устанавливаю обновление" 96\n'
ci='''if [[ -n "${ENDLUME_CI_ARTIFACT_DIR:-}" ]]; then
  mkdir -p "$ENDLUME_CI_ARTIFACT_DIR"
  ASSET="${ENDLUME_CI_ASSET_NAME:-ENDLUME-Studio-1.0.0-alpha.8.39-macos-arm64.zip}"
  /usr/bin/ditto -c -k --keepParent "$BUILT_APP" "$ENDLUME_CI_ARTIFACT_DIR/$ASSET"
  (cd "$ENDLUME_CI_ARTIFACT_DIR" && /usr/bin/shasum -a 256 "$ASSET" > "$ASSET.sha256")
  echo "@@ENDLUME_STAGE|CI artifact ready"
  echo "@@ENDLUME_PROGRESS|100"
  exit 0
fi
'''
if stage10 not in src: raise SystemExit('8.39 CI: stage10 marker missing')
src=src.replace(stage10,ci+stage10,1)

required=[
 'VERSION_EXPECTED="1.0.0-alpha.8.39"',
 'WORK_ROOT="$HOME/.endlume-local-builder"',
 'apply-youtube-fill-8-38.py',
 'apply-performance-fidelity-8-39.py',
 'apply-version-8-39.py',
 'validate-release-8-39.sh',
 'ENDLUME_CI_ARTIFACT_DIR',
 'assert_no_tauri_appledouble',
]
for marker in required:
    if marker not in src: raise SystemExit(f'8.39 CI incomplete: {marker}')
Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY

chmod +x "$PATCHED"
/bin/bash -n "$PATCHED" || fail "generated 8.39 builder syntax failed"
grep -Fq 'VERSION_EXPECTED="1.0.0-alpha.8.39"' "$PATCHED" || fail "8.39 version gate missing"
grep -Fq 'apply-performance-fidelity-8-39.py' "$PATCHED" || fail "8.39 targeted patch missing"
grep -Fq 'validate-release-8-39.sh' "$PATCHED" || fail "8.39 acceptance gate missing"
grep -Fq 'ENDLUME_CI_ARTIFACT_DIR' "$PATCHED" || fail "remote artifact mode missing"
grep -Fq 'WORK_ROOT="$HOME/.endlume-local-builder"' "$PATCHED" || fail "CI builder may still select an external disk"

echo "✅ 8.39 remote builder preflight passed"
/bin/bash "$PATCHED"
