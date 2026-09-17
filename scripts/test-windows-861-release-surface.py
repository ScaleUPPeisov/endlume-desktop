#!/usr/bin/env python3
from pathlib import Path
import json,re
root=Path('.')
main=(root/'src-tauri/src/main.rs').read_text(encoding='utf-8')
render=(root/'src-tauri/src/render.rs').read_text(encoding='utf-8')
updater=(root/'src-tauri/src/updater_windows.rs').read_text(encoding='utf-8')
system=(root/'src-tauri/src/system.rs').read_text(encoding='utf-8')
conf=json.loads((root/'src-tauri/tauri.windows.conf.json').read_text(encoding='utf-8'))
ui=(root/'src/components/ui.tsx').read_text(encoding='utf-8')
settings=(root/'src/pages/SettingsPage.tsx').read_text(encoding='utf-8')
brand=(root/'src/platform-brand.ts').read_text(encoding='utf-8')
assert 'windows_subsystem = "windows"' in main
assert conf['productName']=='ENDLUME YT Studio PEISOV'
assert conf.get('mainBinaryName')=='ENDLUME YT Studio PEISOV'
assert conf['identifier']=='studio.endlume.desktop'
assert 'ENDLUME YT Studio PEISOV' in brand
assert 'PRODUCT_NAME' in ui and 'YT STUDIO PEISOV' in ui
assert 'PRODUCT_NAME' in settings and 'PRODUCT_KICKER' in settings
# FFmpeg/ffprobe must stay Tauri sidecars: tauri-plugin-shell v2 applies CREATE_NO_WINDOW on Windows.
assert 'app.shell().sidecar(name)' in render
assert 'app.shell().sidecar("ffmpeg")' in render
for forbidden in ('Command::new("cmd.exe")','Command::new("powershell")','Command::new("powershell.exe")','Command::new("pwsh")','Command::new("Windows Terminal")'):
    assert forbidden not in render+updater+system, f'visible-console runtime command: {forbidden}'
assert 'update.install(bytes)' in updater
assert 'SHA-256' in updater
print('ENDLUME_WINDOWS_861_RELEASE_SURFACE_GREEN')
