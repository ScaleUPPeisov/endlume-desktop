#!/bin/bash
set -Eeuo pipefail
fail(){ echo "8.40 validation failed: $1" >&2; exit 1; }

[[ -f updates/github/bootstrap.json ]] || fail "bootstrap missing"
[[ -f src-tauri/tauri.conf.json ]] || fail "tauri.conf missing"
[[ -f src/tauri.ts ]] || fail "tauri.ts missing"

python3 - <<'PY'
import json
b=json.load(open('updates/github/bootstrap.json'))
c=json.load(open('src-tauri/tauri.conf.json'))
u=c.get('plugins',{}).get('updater',{})
assert b.get('endpoint') in u.get('endpoints',[]), 'endpoint mismatch'
assert u.get('pubkey')==b.get('pubkey') and u.get('pubkey'), 'pubkey mismatch'
assert c.get('bundle',{}).get('createUpdaterArtifacts') is True, 'createUpdaterArtifacts disabled'
PY

grep -Fq "from '@tauri-apps/plugin-updater'" src/tauri.ts || fail "plugin-updater import missing"
grep -Fq "from '@tauri-apps/plugin-process'" src/tauri.ts || fail "process import missing"
grep -Fq 'await withTimeout(check()' src/tauri.ts || fail "native check missing"
grep -Fq 'downloadAndInstall' src/tauri.ts || fail "native install missing"
grep -Fq 'await relaunch()' src/tauri.ts || fail "relaunch missing"
if grep -Eq "local_update_(check|start|status)" src/tauri.ts; then fail "old local updater frontend survived"; fi

grep -Fq '"updater:default"' src-tauri/capabilities/default.json || fail "updater permission missing"
grep -Fq '"process:default"' src-tauri/capabilities/default.json || fail "process permission missing"

grep -Fq '1.0.0-alpha.8.40' package.json || fail "package version wrong"
grep -Fq '1.0.0-alpha.8.40' src-tauri/tauri.conf.json || fail "tauri version wrong"

echo '✅ ENDLUME 8.40 native updater gate passed'
