#!/bin/bash
set -Eeuo pipefail
REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
TMP_ROOT="$(mktemp -d /tmp/endlume-840-builder.XXXXXX)"
BASE="$TMP_ROOT/BUILD_ENDLUME_839_LOCAL.command"
PATCHED="$TMP_ROOT/BUILD_ENDLUME_840_REAL.command"
cleanup(){ rm -rf "$TMP_ROOT" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo; echo "❌ ENDLUME 8.40 BUILDER: $1"; exit 1; }

echo "ENDLUME Studio 1.0.0-alpha.8.40"
echo "8.39 proven render stack + local VYRON Batch Bridge"
echo
[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"

gh api "repos/$REPO/contents/BUILD_ENDLUME_839_LOCAL.command?ref=$BRANCH" --jq .content | tr -d '\n' | /usr/bin/base64 -D > "$BASE" || fail "не удалось получить proven 8.39 builder"
[[ -s "$BASE" ]] || fail "8.39 builder пуст"

python3 - "$BASE" "$PATCHED" <<'PY'
from pathlib import Path
import sys
meta=Path(sys.argv[1]).read_text(encoding='utf-8')

# Final identity is 8.40, while all 8.39 policy scripts/validators remain unchanged.
old="src=src.replace('VERSION_EXPECTED=\"1.0.0-alpha.8.33\"','VERSION_EXPECTED=\"1.0.0-alpha.8.39\"',1)"
new="src=src.replace('VERSION_EXPECTED=\"1.0.0-alpha.8.33\"','VERSION_EXPECTED=\"1.0.0-alpha.8.40\"',1)"
if old not in meta: raise SystemExit('8.40: 8.39 version transform marker missing')
meta=meta.replace(old,new,1)
meta=meta.replace(" 'VERSION_EXPECTED=\"1.0.0-alpha.8.39\"',"," 'VERSION_EXPECTED=\"1.0.0-alpha.8.40\"',",1)

# 8.32 replay guard: current raw release already has a later updater shape.
marker="src=Path(sys.argv[1]).read_text(encoding='utf-8')\n"
inject="""src=Path(sys.argv[1]).read_text(encoding='utf-8')
replay_marker='python3 scripts/apply-queue-updater-8-32.py\\n'
if replay_marker not in src:
    raise SystemExit('8.40: 8.32 replay insertion marker missing')
replay_fix='python3 -m py_compile scripts/repair-updater-replay-8-32.py\\npython3 scripts/repair-updater-replay-8-32.py\\n'
src=src.replace(replay_marker,replay_fix+replay_marker,1)
"""
if marker not in meta: raise SystemExit('8.40: meta source marker missing')
meta=meta.replace(marker,inject,1)

# Apply bridge only AFTER all proven 8.39 validators, then re-run compile/test gates.
needle="src=src.replace(old_stage,new_stage,1)\n"
extra=r"""src=src.replace(old_stage,new_stage,1)
bridge_marker='node scripts/validate-motion-ui.mjs\n'
bridge_add='''python3 -m py_compile scripts/apply-vyron-bridge-8-40.py
python3 scripts/apply-vyron-bridge-8-40.py
npm run check
npm run build
cargo test --manifest-path src-tauri/Cargo.toml --lib -- --nocapture
cargo check --manifest-path src-tauri/Cargo.toml --target aarch64-apple-darwin
grep -Fq 'mod vyron_bridge;' src-tauri/src/lib.rs
grep -Fq 'vyron_bridge::consume_vyron_batch_request' src-tauri/src/lib.rs
grep -Fq 'consumeVyronBatch:' src/tauri.ts
grep -Fq '<VyronBatchBridge/>' src/pages/App.tsx
grep -Fq 'onClick={enqueue}' src/pages/ProjectPage.tsx
grep -Fq "openEditor({kind:'subscribe'})" src/pages/ProjectPage.tsx
grep -Fq "openEditor({kind:'effects'})" src/pages/ProjectPage.tsx
echo 'ENDLUME 8.40 VYRON bridge compile + regression gates: PASS'
'''
if bridge_marker not in src:
    raise SystemExit('8.40: final motion validator marker missing')
src=src.replace(bridge_marker,bridge_marker+bridge_add,1)

# CI mode packages the already-tested .app instead of replacing /Applications.
stage10='stage "10/10 Устанавливаю обновление" 96\n'
ci='''if [[ -n "${ENDLUME_CI_ARTIFACT_DIR:-}" ]]; then
  mkdir -p "$ENDLUME_CI_ARTIFACT_DIR"
  ASSET="${ENDLUME_CI_ASSET_NAME:-ENDLUME-Studio-1.0.0-alpha.8.40-macos-arm64.zip}"
  /usr/bin/ditto -c -k --keepParent "$BUILT_APP" "$ENDLUME_CI_ARTIFACT_DIR/$ASSET"
  (cd "$ENDLUME_CI_ARTIFACT_DIR" && /usr/bin/shasum -a 256 "$ASSET" > "$ASSET.sha256")
  echo "@@ENDLUME_STAGE|CI artifact ready"
  echo "@@ENDLUME_PROGRESS|100"
  exit 0
fi
'''
if stage10 not in src:
    raise SystemExit('8.40: stage10 marker missing')
src=src.replace(stage10,ci+stage10,1)
"""
if needle not in meta: raise SystemExit('8.40: 8.39 stage replacement marker missing')
meta=meta.replace(needle,extra,1)

# Update outer preflight expectations only; keep 8.39 script names untouched.
meta=meta.replace('ENDLUME Studio 1.0.0-alpha.8.39','ENDLUME Studio 1.0.0-alpha.8.40',1)
meta=meta.replace('❌ ENDLUME 8.39 DIRECT','❌ ENDLUME 8.40 DIRECT',1)
meta=meta.replace("grep -Fq 'VERSION_EXPECTED=\"1.0.0-alpha.8.39\"' \"$PATCHED\"","grep -Fq 'VERSION_EXPECTED=\"1.0.0-alpha.8.40\"' \"$PATCHED\"",1)
meta=meta.replace('✅ DIRECT 8.39 preflight passed','✅ DIRECT 8.40 preflight passed',1)
meta=meta.replace('✅ 8.39 bridge FIXED','✅ 8.40 builder replay guard active',1)

Path(sys.argv[2]).write_text(meta,encoding='utf-8')
PY

chmod +x "$PATCHED"
/bin/bash -n "$PATCHED" || fail "generated 8.40 meta-builder syntax failed"
grep -Fq 'VERSION_EXPECTED="1.0.0-alpha.8.40"' "$PATCHED" || fail "8.40 final version gate missing"
grep -Fq 'repair-updater-replay-8-32.py' "$PATCHED" || fail "8.32 replay guard missing"
grep -Fq 'apply-vyron-bridge-8-40.py' "$PATCHED" || fail "VYRON bridge patch missing"
grep -Fq 'cargo test --manifest-path src-tauri/Cargo.toml --lib' "$PATCHED" || fail "VYRON Rust tests missing"
grep -Fq 'ENDLUME_CI_ARTIFACT_DIR' "$PATCHED" || fail "CI artifact mode missing"
grep -Fq 'stage "10/10 Устанавливаю обновление" 96' "$PATCHED" || fail "safe stage10 missing"

echo "✅ ENDLUME 8.40 preflight PASS"
/bin/bash "$PATCHED"
