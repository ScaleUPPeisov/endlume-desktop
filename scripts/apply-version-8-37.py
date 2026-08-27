from pathlib import Path
import re
version='1.0.0-alpha.8.37'
for file_name in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

p=Path('src/components/ReleaseHistory.tsx')
h=p.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.37',date:'27.08.2026',current:true,title:'Remote Update Center',items:[
    'ENDLUME больше не собирает обновления на пользовательском Mac: npm/Rust/Tauri-компиляция перенесена на удалённый macOS runner.',
    'Настройки → Обновления теперь разделены на Проверить обновления и Установить и перезапустить.',
    'Готовая .app скачивается из приватного GitHub release, проверяется SHA-256, Bundle ID, версия и codesign перед заменой.',
    'При установке используется atomic swap с предыдущей .app и rollback при ошибке.',
    '1080p Fidelity Lock, original MP3 bitstream-copy, Preview Shield и AppleDouble-защита сохранены.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.37'" not in h:
    if marker not in h: raise SystemExit('8.37: release history marker missing')
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')
print('ENDLUME alpha.8.37 version/history synced')
