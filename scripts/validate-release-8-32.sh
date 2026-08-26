#!/bin/bash
set -euo pipefail

fail(){ echo "FAIL: $1" >&2; exit 1; }
pass(){ echo "PASS: $1"; }

STORE=src/store.ts
PROJECT=src/pages/ProjectPage.tsx
APP=src/pages/App.tsx
TAURI=src/tauri.ts
LIB=src-tauri/src/lib.rs
UPD=src-tauri/src/updater_local.rs
SETTINGS=src/pages/SettingsPage.tsx
PKG=package.json

for f in "$STORE" "$PROJECT" "$APP" "$TAURI" "$LIB" "$UPD" "$SETTINGS" "$PKG"; do test -f "$f" || fail "missing $f"; done

grep -Fq 'syncQueueProjects' "$STORE" || fail 'store queue sync missing'
grep -Fq 'projects:s.projects' "$STORE" || fail 'render projects are not persisted'
grep -Fq '!known.has(n.id)' "$STORE" || fail 'appendProjects still dedupes by path'
pass 'frontend queue store keeps repeated jobs and persists projects'

grep -Fq 'const queuedProjects=draftProjects.map' "$PROJECT" || fail 'unique enqueue list missing'
grep -Fq 'Math.random().toString(36)' "$PROJECT" || fail 'unique queue job id missing'
grep -Fq 'await api.enqueue(queuedProjects' "$PROJECT" || fail 'backend still receives non-unique draft ids'
pass 'same folder can be enqueued repeatedly with unique job IDs'

grep -Fq "listen<any>('queue-changed'" "$APP" || fail 'queue-changed listener missing'
grep -Fq 'api.queueSnapshot().then(syncBackendQueue)' "$APP" || fail 'startup queue snapshot missing'
grep -Fq 'function syncBackendQueue' "$APP" || fail 'queue reconcile helper missing'
pass 'render page is synchronized with backend active/pending queue'

grep -Fq "invoke<Info>('local_update_check')" "$TAURI" || fail 'in-app update check missing'
grep -Fq "invoke<Status>('local_update_start')" "$TAURI" || fail 'in-app update start missing'
grep -Fq "invoke<Status>('local_update_status')" "$TAURI" || fail 'in-app update progress missing'
! grep -Fq "from '@tauri-apps/plugin-updater'" "$TAURI" || fail 'old public updater still used by frontend'
pass 'frontend updater uses private local update engine'

grep -Fq 'mod updater_local;' "$LIB" || fail 'Rust updater module not registered'
grep -Fq 'updater_local::local_update_check' "$LIB" || fail 'updater commands not registered'
grep -Fq 'Command::new("/usr/bin/nohup")' "$UPD" || fail 'updater does not detach hidden build'
grep -Fq 'BUILD_ENDLUME_' "$UPD" || fail 'builder path validation missing'
grep -Fq '@@ENDLUME_STAGE|' "$UPD" || fail 'live update stage parser missing'
pass 'hidden updater runs without Terminal and exposes live stages'

grep -Fq 'Terminal и командная строка не открываются' "$SETTINGS" || fail 'Settings does not explain in-app update mode'
grep -Fq '1.0.0-alpha.8.32' "$SETTINGS" || fail 'Settings version is not 8.32'
grep -Fq '"version": "1.0.0-alpha.8.32"' "$PKG" || fail 'package version is not 8.32'
pass '8.32 UI/version wiring is present'

echo 'ENDLUME 8.32 queue + in-app updater gate passed.'
