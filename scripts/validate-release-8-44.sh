#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-ffmpeg}"
FFPROBE="${2:-ffprobe}"
fail(){ echo "8.44 validation failed: $1" >&2; exit 1; }
pass(){ echo "PASS: $1"; }

for f in package.json src-tauri/tauri.conf.json src-tauri/src/lib.rs src-tauri/src/render.rs src-tauri/src/vyron_bridge.rs src-tauri/src/vyron_bridge_tests.rs src/tauri.ts src/pages/App.tsx src/pages/ProjectPage.tsx src/components/VyronBatchBridge.tsx scripts/validate-real-60fps.sh; do
  [[ -f "$f" ]] || fail "missing $f"
done

grep -Fq '1.0.0-alpha.8.44' package.json || fail 'package version is not 8.44'
grep -Fq '1.0.0-alpha.8.44' src-tauri/tauri.conf.json || fail 'Tauri version is not 8.44'
grep -Fq "version:'1.0.0-alpha.8.44'" src/components/ReleaseHistory.tsx || fail '8.44 release history missing'
pass '8.44 identity/history present'

# Full 8.43 Real 60 FPS gate, adapted only for the expected final version.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
sed 's/1\.0\.0-alpha\.8\.43/1.0.0-alpha.8.44/g' scripts/validate-real-60fps.sh > "$TMP/validate-real-60fps-844.sh"
chmod +x "$TMP/validate-real-60fps-844.sh"
"$TMP/validate-real-60fps-844.sh" "$FFMPEG" "$FFPROBE"
pass 'complete 8.43 CFR30/CFR60 render contract survives in 8.44'

# Native VYRON bridge.
grep -Fq 'mod vyron_bridge;' src-tauri/src/lib.rs || fail 'native VYRON module missing'
grep -Fq 'mod vyron_bridge_tests;' src-tauri/src/lib.rs || fail 'native VYRON tests missing'
grep -Fq 'vyron_bridge::consume_vyron_batch_request' src-tauri/src/lib.rs || fail 'consume command missing'
grep -Fq 'vyron_bridge::load_vyron_batch_manifest' src-tauri/src/lib.rs || fail 'manifest command missing'
grep -Fq 'vyron_bridge::report_vyron_render' src-tauri/src/lib.rs || fail 'render report command missing'
grep -Fq 'consumeVyronBatch:' src/tauri.ts || fail 'frontend consume API missing'
grep -Fq 'loadVyronBatch:' src/tauri.ts || fail 'frontend manifest API missing'
grep -Fq 'reportVyronRender:' src/tauri.ts || fail 'frontend render report API missing'
grep -Fq '<VyronBatchBridge/>' src/pages/App.tsx || fail 'VYRON bridge mount missing'
pass 'local VYRON batch bridge is fully wired'

# Existing manual ENDLUME behavior must stay intact.
grep -Fq 'onClick={enqueue}' src/pages/ProjectPage.tsx || fail 'manual enqueue button changed'
grep -Fq "openEditor({kind:'effects'})" src/pages/ProjectPage.tsx || fail 'Effects editor button changed'
grep -Fq "openEditor({kind:'subscribe'})" src/pages/ProjectPage.tsx || fail 'Subscribe editor button changed'
pass 'manual render / Effects / Subscribe controls preserved'

# Bridge is local-only: no external AI/YouTube API dependencies in the bridge files.
if grep -Eiq 'youtube|googleapis|openai|claude|gemini' src-tauri/src/vyron_bridge.rs src/components/VyronBatchBridge.tsx; then
  fail 'external API reference found inside local VYRON bridge'
fi
pass 'VYRON bridge remains local-only'

# Signed online updater introduced in 8.42 must still be the active path.
grep -Fq '@tauri-apps/plugin-updater' src/tauri.ts || fail 'Tauri updater frontend missing'
grep -Fq 'downloadAndInstall' src/tauri.ts || fail 'signed updater install path missing'
grep -Fq 'tauri_plugin_updater::Builder::new().build()' src-tauri/src/lib.rs || fail 'native updater plugin missing'
if grep -Fq 'updater_local::' src-tauri/src/lib.rs; then fail 'legacy updater backend returned'; fi
pass '8.42 signed online updater preserved'

echo 'ENDLUME 8.44 VYRON Bridge + full 8.43 regression gate passed.'
