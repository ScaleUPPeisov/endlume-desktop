from pathlib import Path
import re

version='1.0.0-alpha.8.30'

for file_name in ['src-tauri/Cargo.toml','src-tauri/tauri.conf.json']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

for file_name in ['src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/RenderPage.tsx','src/pages/ProjectPage.tsx']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    text=text.replace('Stability Gate: ~1 ГБ / 2 ч + exact MP3 + clean install','Stability Gate 2: clean install + exact MP3 + ~1 ГБ / 2 ч')
    p.write_text(text,encoding='utf-8')

p=Path('src/components/ReleaseHistory.tsx')
h=p.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.30',date:'26.08.2026',current:true,title:'Stability Gate 2: установка без patch-drift + exact MP3 + компактный 2ч render',items:[
    'Установщик собирает проект только из чистого fresh-clone и не использует старый локальный source-cache.',
    'Hybrid Fidelity patcher стал идемпотентным: повторная установка не зависит от точной minified-строки Subscribe.',
    'Перед заменой приложения проходят Python syntax, TypeScript, Vite, Rust, Render, Effects, Subscribe, 4K fidelity и exact-MP3 runtime gates.',
    'Финальная ENDLUME Studio.app дополнительно проверяется уже со встроенными FFmpeg/FFprobe.',
    'Совместимые MP3 копируются без повторного lossy-кодирования; при несовместимости качество имеет приоритет над размером.',
    'Для типового проекта 1 картинка + небольшие Effects/Subscribe цель остаётся около 1 ГБ на 2 часа при visually-lossless 4K gate.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.30'" not in h:
    if marker not in h: raise SystemExit('8.30 UI: release history marker missing')
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')

print('ENDLUME alpha.8.30 version/UI sync applied')
