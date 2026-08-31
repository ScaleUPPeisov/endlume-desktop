from pathlib import Path
import re

version='1.0.0-alpha.8.40'
for file_name in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    p=Path(file_name)
    text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

p=Path('src/pages/SettingsPage.tsx')
s=p.read_text(encoding='utf-8')
s=re.sub(r'Обновлено <b>[^<]+</b>','Обновлено <b>31.08.2026</b>',s,count=1)
about_marker='<span>UI <b>Tauri 2</b></span>'
owner_rows='<span>Создатель <b>Kirill Peisov</b></span><span>Email <b>peisov.business@gmail.com</b></span>'
if 'Kirill Peisov' not in s:
    if about_marker not in s: raise SystemExit('8.40: About UI marker missing')
    s=s.replace(about_marker,about_marker+owner_rows,1)
p.write_text(s,encoding='utf-8')

p=Path('src/components/ReleaseHistory.tsx')
h=p.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.40',date:'31.08.2026',current:true,title:'Native Signed Updates',items:[
    'Чистый bootstrap интернет-обновлений на последней доказанно стабильной базе 8.38 — без запуска проблемной цепочки 8.39 при установке.',
    'Update Center переведён на официальный Tauri updater: проверка, скачивание, проверка подписи, установка и перезапуск выполняются внутри приложения.',
    'GitHub Actions, Cloudflare, VPS, IP и SSH больше не нужны установленному ENDLUME для получения обновлений.',
    'Исходный репозиторий остаётся приватным; публичный канал содержит только подписанные updater-пакеты и latest.json.',
    'Исправления 60 FPS/crossfade/chroma из ветки 8.39 будут возвращены отдельным удалённым релизом после перехода на новую систему обновлений.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.40'" not in h:
    if marker not in h: raise SystemExit('8.40: release history marker missing')
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')
print('ENDLUME alpha.8.40 updater-bootstrap version/history/About synced')
