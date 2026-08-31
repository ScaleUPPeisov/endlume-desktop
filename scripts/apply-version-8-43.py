from pathlib import Path
import re

version='1.0.0-alpha.8.43'
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
entry="""  {version:'1.0.0-alpha.8.43',date:'31.08.2026',current:true,title:'Real 60 FPS Output Validation',items:[
    'Финальный MP4 теперь проходит строгую проверку r_frame_rate + avg_frame_rate + фактического числа видеокадров/пакетов перед статусом «Готово».',
    'Режимы разделены корректно: 30 FPS → CFR 30, 60 FPS → CFR 60. Старый скрытый 60→30 clamp запрещён.',
    'Short-master, Effects и Subscribe кодируются CFR с сохранением proven 500k speed/size budget; двухчасовой final остаётся stream-copy.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.43'" not in h:
    if marker not in h: raise SystemExit('8.43: release history marker missing')
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')
print('ENDLUME alpha.8.43 Real 60 FPS Output Validation version/history synced')
