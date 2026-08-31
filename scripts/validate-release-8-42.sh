#!/bin/bash
set -Eeuo pipefail

fail(){ echo "FAIL: $1" >&2; exit 1; }
pass(){ echo "PASS: $1"; }

python3 - <<'PY' || exit 1
from pathlib import Path
import json,re

# Native frontend updater only.
s=Path('src/tauri.ts').read_text(encoding='utf-8')
for bad in ('local_update_check','local_update_start','local_update_status'):
    assert bad not in s, bad
for good in ("@tauri-apps/plugin-updater","@tauri-apps/plugin-process","@tauri-apps/api/app","check()","downloadAndInstall","relaunch()","getVersion()"):
    assert good in s, good
print('PASS: frontend uses official Tauri updater only')

# Runtime has no legacy updater backend registration.
r=Path('src-tauri/src/lib.rs').read_text(encoding='utf-8')
assert 'mod updater_local;' not in r
assert 'updater_local::' not in r
assert 'tauri_plugin_process::init()' in r
assert 'tauri_plugin_updater::Builder::new().build()' in r
print('PASS: Rust runtime contains only native updater/process plugins')

# Tauri config and signed static endpoint.
b=json.loads(Path('updates/github/bootstrap.json').read_text(encoding='utf-8'))
cfg=json.loads(Path('src-tauri/tauri.conf.json').read_text(encoding='utf-8'))
assert cfg['identifier']=='studio.endlume.desktop'
assert cfg['bundle']['createUpdaterArtifacts'] is True
up=cfg['plugins']['updater']
assert up['endpoints']==[b['endpoint']]
assert up['pubkey'] and up['pubkey']==b['pubkey']
assert b['endpoint']=='https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/latest.json'
print('PASS: signed updater endpoint/pubkey/createUpdaterArtifacts are correct')

cap=json.loads(Path('src-tauri/capabilities/default.json').read_text(encoding='utf-8'))
perms=cap['permissions']
assert 'updater:default' in perms
assert 'process:default' in perms
print('PASS: updater/process capabilities enabled')

ui=Path('src/pages/SettingsPage.tsx').read_text(encoding='utf-8')
assert 'appVersion' in ui
assert 'api.appVersion().then(setAppVersion)' in ui
assert 'ПРОВЕРИТЬ ОБНОВЛЕНИЯ' in ui
assert 'Доступна ENDLUME' in ui
assert 'локальный builder' not in ui
assert '1.0.0-alpha.8.19' not in ui
print('PASS: Settings uses runtime version and online updater wording')

pkg=json.loads(Path('package.json').read_text(encoding='utf-8'))
assert pkg['version']=='1.0.0-alpha.8.42',pkg['version']
assert cfg['version']=='1.0.0-alpha.8.42',cfg['version']
print('PASS: version 1.0.0-alpha.8.42')

# Protect unrelated render contract by asserting known 8.41 invariants still exist.
render=Path('src-tauri/src/render.rs').read_text(encoding='utf-8')
assert 'fps' in render
assert '500' in render
store=Path('src/store.ts').read_text(encoding='utf-8')
assert 'crossfade' in store
print('PASS: updater-only release did not remove guarded render/store invariants')
PY

# Workflow must not launch the app and must use self-hosted production labels.
WF='.github/workflows/endlume-self-hosted-release.yml'
[[ -f "$WF" ]] || fail 'self-hosted workflow missing'
grep -Fq 'runs-on: [self-hosted, macOS, ARM64, endlume, macos-arm64]' "$WF" || fail 'self-hosted labels missing'
if grep -Fq '/usr/bin/open "$DEST"' "$WF"; then fail 'workflow still launches ENDLUME'; fi
if grep -Fq "open \"/Applications/ENDLUME Studio.app\"" "$WF"; then fail 'workflow still launches ENDLUME'; fi
pass 'workflow does not launch ENDLUME from Actions job'

echo '✅ ENDLUME 8.42 updater-only regression gate passed'
