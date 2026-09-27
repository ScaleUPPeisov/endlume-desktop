from pathlib import Path
import re

version='1.0.0-alpha.8.39'
for file_name in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

p=Path('src/pages/SettingsPage.tsx')
s=p.read_text(encoding='utf-8')
s=re.sub(r'Обновлено <b>[^<]+</b>','Обновлено <b>30.08.2026</b>',s,count=1)
about_marker='<span>UI <b>Tauri 2</b></span>'
owner_rows='<span>Создатель <b>Kirill Peisov</b></span><span>Email <b>peisov.business@gmail.com</b></span>'
if 'Kirill Peisov' not in s:
    if about_marker not in s: raise SystemExit('8.39: About UI marker missing')
    s=s.replace(about_marker,about_marker+owner_rows,1)
p.write_text(s,encoding='utf-8')

p=Path('src/components/ReleaseHistory.tsx')
h=p.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.39',date:'30.08.2026',current:true,title:'60 FPS Stability + Audio/Chroma',items:[
    'One-image рендер и Effects/эквалайзер теперь реально работают в 60 FPS; 1920×1080 YouTube Fill без чёрных полос сохранён.',
    'Завершённые очереди больше не копятся в localStorage, а render-progress обновляется пакетно — исправлены подвисания интерфейса после больших очередей.',
    'Кроссфейд снова применяется. При включённом crossfade треки сводятся в непрерывную HQ 320 kbit/s дорожку без секундных пауз; при выключенном crossfade сохраняется exact MP3 copy.',
    'Chromakey получил реальный despill в Render и Live Preview, включая отдельную регулировку удаления зелёного ореола.',
    'Скоростная short-master/stream-copy архитектура, размер около 1 GB, быстрый финальный mux, Effects/Subscribe, Noise removal и Remote Update Center сохранены.',
    'О программе: добавлены Kirill Peisov и peisov.business@gmail.com.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.39'" not in h:
    if marker not in h: raise SystemExit('8.39: release history marker missing')
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')

print('ENDLUME alpha.8.39 version/history/owner info synced')
