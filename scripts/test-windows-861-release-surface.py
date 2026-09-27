#!/usr/bin/env python3
from pathlib import Path
import json
root=Path('.')
main=(root/'src-tauri/src/main.rs').read_text(encoding='utf-8')
render=(root/'src-tauri/src/render.rs').read_text(encoding='utf-8')
updater=(root/'src-tauri/src/updater_windows.rs').read_text(encoding='utf-8')
system=(root/'src-tauri/src/system.rs').read_text(encoding='utf-8')
builder=(root/'scripts/build-windows.ps1').read_text(encoding='utf-8')
publisher=(root/'scripts/selfhosted-release-windows.ps1').read_text(encoding='utf-8')
worker=(root/'infra/cloudflare-update/src/index.js').read_text(encoding='utf-8')
conf=json.loads((root/'src-tauri/tauri.windows.conf.json').read_text(encoding='utf-8'))
package=json.loads((root/'package.json').read_text(encoding='utf-8'))
ui=(root/'src/components/ui.tsx').read_text(encoding='utf-8')
settings=(root/'src/pages/SettingsPage.tsx').read_text(encoding='utf-8')
brand=(root/'src/platform-brand.ts').read_text(encoding='utf-8')
assert package['version'] in {'1.0.0-alpha.8.61','1.0.0-alpha.8.62'}
assert 'windows_subsystem = "windows"' in main
assert conf['productName']=='ENDLUME YT Studio PEISOV'
assert conf.get('mainBinaryName')=='ENDLUME YT Studio PEISOV'
assert conf['identifier']=='studio.endlume.desktop'
assert conf['bundle']['publisher']=='PEISOV'
assert conf['bundle']['shortDescription']=='ENDLUME YT Studio PEISOV'
assert conf['bundle']['longDescription']=='ENDLUME YT Studio PEISOV'
assert conf['bundle']['windows']['nsis']['startMenuFolder']=='ENDLUME YT Studio PEISOV'
assert conf['bundle']['windows']['nsis']['installerIcon']=='icons/icon.ico'
assert conf['bundle']['windows']['nsis']['uninstallerIcon']=='icons/icon.ico'
assert 'ENDLUME YT Studio PEISOV' in brand
assert 'PRODUCT_NAME' in ui and 'YT STUDIO PEISOV' in ui
assert 'PRODUCT_NAME' in settings and 'PRODUCT_KICKER' in settings
assert 'ENDLUME-YT-Studio-PEISOV-Setup-$Version-x64.exe' in builder
# FFmpeg/ffprobe stay Tauri sidecars; tauri-plugin-shell v2 uses CREATE_NO_WINDOW on Windows.
assert 'app.shell().sidecar(name)' in render
assert 'app.shell().sidecar("ffmpeg")' in render
# Native Windows Explorer calls are explicitly hidden too.
assert 'hidden_windows_command("explorer.exe")' in system
assert 'creation_flags(0x0800_0000)' in system
assert 'GetSystemPowerStatus' in system and 'windows_power_status()' in system
for forbidden in ('Command::new("cmd.exe")','Command::new("powershell")','Command::new("powershell.exe")','Command::new("pwsh")','Command::new("Windows Terminal")'):
    assert forbidden not in render+updater+system, f'visible-console runtime command: {forbidden}'
# Windows updater is fail-closed end-to-end: signed package + publisher SHA-256 + API passthrough + client verification.
assert 'update.download(' in updater and 'update.install(bytes)' in updater
assert 'expected_sha256' in updater and 'sha256_hex(&bytes)' in updater and 'actual!=expected' in updater
assert 'Get-FileHash -Algorithm SHA256' in publisher
assert 'sha256 = $Sha256' in publisher
assert "platform.startsWith('windows-')&&!validSha256(manifest.sha256)" in worker
assert 'response.sha256=manifest.sha256.trim().toLowerCase()' in worker
print('ENDLUME_WINDOWS_861_RELEASE_SURFACE_GREEN',package['version'])
