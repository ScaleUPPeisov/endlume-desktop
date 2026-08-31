from pathlib import Path
import re

version='1.0.0-alpha.8.42'
for file_name in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    p=Path(file_name)
    text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

p=Path('src/pages/SettingsPage.tsx')
s=p.read_text(encoding='utf-8')
s=re.sub(r'Обновлено <b>[^<]+</b>','Обновлено <b>31.08.2026</b>',s,count=1)
p.write_text(s,encoding='utf-8')

p=Path('src/components/ReleaseHistory.tsx')
h=p.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.42',date:'31.08.2026',current:true,title:'Online Update System validation',items:[
    'Updater-only validation release. Рендер, Effects, очередь, качество, 60 FPS и остальные функции ENDLUME не изменялись.',
    'Официальный Tauri v2 updater: check → signed downloadAndInstall → relaunch.',
    'Версия в Настройках берётся из реально установленного приложения через getVersion().'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.42'" not in h:
    if marker not in h: raise SystemExit('8.42: release history marker missing')
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')
print('ENDLUME alpha.8.42 updater validation version/history synced')
