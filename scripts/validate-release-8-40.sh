#!/bin/bash
set -Eeuo pipefail
fail(){ echo "8.40 validation failed: $1" >&2; exit 1; }

for f in updates/github/bootstrap.json src-tauri/tauri.conf.json src/tauri.ts src/pages/SettingsPage.tsx package.json; do
  [[ -f "$f" ]] || fail "missing $f"
done

python3 - <<'PY'
import json
EXPECTED='https://github.com/ScaleUPPeisov/scaleup-site/releases/download/endlume-stable/latest.json'
b=json.load(open('updates/github/bootstrap.json'))
c=json.load(open('src-tauri/tauri.conf.json'))
u=c.get('plugins',{}).get('updater',{})
assert b.get('endpoint')==EXPECTED, 'bootstrap endpoint wrong'
assert u.get('endpoints')==[EXPECTED], 'tauri endpoint mismatch'
assert u.get('pubkey')==b.get('pubkey') and u.get('pubkey'), 'pubkey mismatch/empty'
assert c.get('bundle',{}).get('createUpdaterArtifacts') is True, 'main createUpdaterArtifacts disabled'
assert c.get('identifier')=='studio.endlume.desktop', 'bundle identifier changed'
PY

grep -Fq "from '@tauri-apps/plugin-updater'" src/tauri.ts || fail "plugin-updater import missing"
grep -Fq "from '@tauri-apps/plugin-process'" src/tauri.ts || fail "process import missing"
grep -Fq "from '@tauri-apps/api/app'" src/tauri.ts || fail "getVersion import missing"
grep -Fq 'await getVersion()' src/tauri.ts || fail "runtime current version lookup missing"
grep -Fq 'await withTimeout(check()' src/tauri.ts || fail "native check missing"
grep -Fq 'downloadAndInstall' src/tauri.ts || fail "native install missing"
grep -Fq 'await relaunch()' src/tauri.ts || fail "relaunch missing"
if grep -Eq "local_update_(check|start|status)" src/tauri.ts; then fail "old local updater frontend survived"; fi

grep -Fq 'const checkUpdate=async()=>{' src/pages/SettingsPage.tsx || fail "two-step check handler missing"
grep -Fq 'const installUpdate=async()=>{' src/pages/SettingsPage.tsx || fail "explicit install handler missing"
grep -Fq 'onClick={checkUpdate}' src/pages/SettingsPage.tsx || fail "check button not wired"
grep -Fq 'onClick={installUpdate}' src/pages/SettingsPage.tsx || fail "install button not wired"
grep -Fq 'ПРОВЕРИТЬ ОБНОВЛЕНИЯ' src/pages/SettingsPage.tsx || fail "check button label missing"
grep -Fq 'Доступна ENDLUME' src/pages/SettingsPage.tsx || fail "available-version UI missing"
grep -Fq "'ОБНОВИТЬ'" src/pages/SettingsPage.tsx || fail "explicit update button label missing"
grep -Fq 'Установлена актуальная alpha-версия' src/pages/SettingsPage.tsx || fail "latest-version state missing"
grep -Fq 'Подписанные обновления ENDLUME' src/pages/SettingsPage.tsx || fail "signed-updater Settings explanation missing"
if grep -Fq 'ПРОВЕРИТЬ И ОБНОВИТЬ' src/pages/SettingsPage.tsx; then fail "old combined updater button survived"; fi
if grep -Fq 'локальный builder' src/pages/SettingsPage.tsx; then fail "old local-builder recommendation survived"; fi
if grep -Fq 'удалённом macOS-сервере' src/pages/SettingsPage.tsx; then fail "old remote-builder explanation survived"; fi

grep -Fq '"updater:default"' src-tauri/capabilities/default.json || fail "updater permission missing"
grep -Fq '"process:default"' src-tauri/capabilities/default.json || fail "process permission missing"

grep -Fq '1.0.0-alpha.8.40' package.json || fail "package version wrong"
grep -Fq '1.0.0-alpha.8.40' src-tauri/tauri.conf.json || fail "tauri version wrong"

echo '✅ ENDLUME 8.40 native updater + two-step Update Center gate passed'
