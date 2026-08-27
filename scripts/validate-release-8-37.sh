#!/bin/bash
set -Eeuo pipefail
fail(){ echo "FAIL: $1" >&2; exit 1; }
pass(){ echo "PASS: $1"; }
UPD=src-tauri/src/updater_local.rs
TS=src/tauri.ts
SETTINGS=src/pages/SettingsPage.tsx
PKG=package.json
for f in "$UPD" "$TS" "$SETTINGS" "$PKG"; do test -f "$f" || fail "missing $f"; done

grep -Fq 'm.channel!="remote-binary"' "$UPD" || fail 'remote-binary channel guard missing'
grep -Fq 'release download' "$UPD" || fail 'prebuilt release download missing'
grep -Fq 'shasum -a 256 -c' "$UPD" || fail 'SHA-256 verification missing'
grep -Fq 'CFBundleIdentifier' "$UPD" || fail 'Bundle ID validation missing'
grep -Fq 'CFBundleShortVersionString' "$UPD" || fail 'version validation missing'
grep -Fq 'codesign --verify --deep --strict' "$UPD" || fail 'codesign validation missing'
grep -Fq '/Applications/.ENDLUME Studio.remote-previous.app' "$UPD" || fail 'rollback slot missing'
! grep -Fq 'cargo check' "$UPD" || fail 'remote updater still compiles Rust locally'
! grep -Fq 'npm install' "$UPD" || fail 'remote updater still installs npm locally'
! grep -Fq 'BUILD_ENDLUME_' "$UPD" || fail 'remote updater still executes local builder'
pass 'backend downloads and atomically installs a prebuilt release'

grep -Fq "channel:'remote-binary'" "$TS" || fail 'frontend channel is not remote-binary'
grep -Fq 'ПРОВЕРИТЬ ОБНОВЛЕНИЯ' "$SETTINGS" || fail 'check button missing'
grep -Fq 'УСТАНОВИТЬ И ПЕРЕЗАПУСТИТЬ' "$SETTINGS" || fail 'install/restart button missing'
grep -Fq 'Локальная компиляция на Mac больше не используется.' "$SETTINGS" || fail 'remote-update UX copy missing'
grep -Fq '"version": "1.0.0-alpha.8.37"' "$PKG" || fail 'package version is not 8.37'
pass 'Settings Update Center is wired for remote binary updates'

echo 'ENDLUME 8.37 Remote Update Center gate passed.'
