from pathlib import Path
import re
version='1.0.0-alpha.8.38'
for file_name in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

p=Path('src/components/ReleaseHistory.tsx')
h=p.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.38',date:'27.08.2026',current:true,title:'YouTube Fill 16:9 — No Black Bars',items:[
    'One-image YouTube рендер всегда заполняет весь кадр 1920×1080 без letterbox/pillarbox.',
    'Вместо decrease + pad используется increase + center crop: изображения не 16:9 слегка обрезаются по краям, а не дополняются чёрными полосами.',
    'Lanczos + accurate rounding, x265-first CRF18, original MP3 bitstream-copy, Preview Shield и Remote Update Center сохранены.',
    'Release gate отдельно проверяет квадратный и вертикальный исходник: итог должен быть ровно 1920×1080 и pipeline не должен содержать pad.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.38'" not in h:
    if marker not in h: raise SystemExit('8.38: release history marker missing')
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')
print('ENDLUME alpha.8.38 version/history synced')
