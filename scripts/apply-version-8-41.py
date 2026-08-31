from pathlib import Path
import re

version='1.0.0-alpha.8.41'
for file_name in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    p=Path(file_name)
    text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

p=Path('src/pages/SettingsPage.tsx')
s=p.read_text(encoding='utf-8')
s=re.sub(r'Обновлено <b>[^<]+</b>','Обновлено <b>31.08.2026</b>',s,count=1)
if 'Kirill Peisov' not in s:
    marker='<span>UI <b>Tauri 2</b></span>'
    if marker not in s: raise SystemExit('8.41: About marker missing')
    s=s.replace(marker,marker+'<span>Создатель <b>Kirill Peisov</b></span><span>Email <b>peisov.business@gmail.com</b></span>',1)
p.write_text(s,encoding='utf-8')

p=Path('src/components/ReleaseHistory.tsx')
h=p.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.41',date:'31.08.2026',current:true,title:'60 FPS • Stability • Gapless Audio • Chroma',items:[
    'Smart/Fidelity render снова работает в реальных 60 FPS без изменения проверенного 500k видеобюджета и быстрого short-master pipeline.',
    'Effects/Equalizer получают motion-interpolated 60 FPS cache и 60 FPS Live Preview вместо простого дублирования 25/30 FPS кадров.',
    'История 100+ рендеров больше не сериализуется в localStorage на каждом progress event; UI progress синхронизируется через requestAnimationFrame.',
    'Crossfade 3 сек восстановлен. Обработанная музыка — HQ 320 кбит/с с нормализованными timestamps и непрерывной long-audio дорожкой без секундных пауз.',
    'Chromakey получил despill с сохранением настройки, новый default 0.35 и отдельный регулятор для удаления зелёного/синего ореола.',
    'О программе: Kirill Peisov • peisov.business@gmail.com. Обновления устанавливаются штатным подписанным Tauri updater внутри ENDLUME.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.41'" not in h:
    if marker not in h: raise SystemExit('8.41: release history marker missing')
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')
print('ENDLUME alpha.8.41 version/history synced')
