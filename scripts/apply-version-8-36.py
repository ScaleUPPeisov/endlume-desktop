from pathlib import Path
import re

version='1.0.0-alpha.8.36'
for file_name in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

p=Path('src/components/ReleaseHistory.tsx')
h=p.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.36',date:'27.08.2026',current:true,title:'1080p Fidelity Lock',items:[
    'One-image проекты теперь рендерятся строго 1920×1080: 4K больше не тратит битрейт впустую при лимите около 1 ГБ.',
    'Исходная картинка масштабируется один раз напрямую из оригинала фильтром Lanczos + accurate rounding.',
    'Короткий master кодируется x265-first: CRF 18 защищает первый I-frame от мозаики, VBV 550 кбит/с ограничивает динамические Effects, VideoToolbox остаётся fallback.',
    '30 FPS, H.265, original MP3 bitstream-copy, отключение crossfade/LUFS/ambient в one-image Fidelity Lock сохранены.',
    'Контрольный gate проверяет точные 1920×1080, SSIM первого кадра, динамический bitrate budget и скорость короткого master.',
    'AppleDouble build-workspace shield, Preview Shield v6, очередь, updater и удаление Noise 1/2 сохранены.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.36'" not in h:
    if marker not in h: raise SystemExit('8.36: release history marker missing')
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')
print('ENDLUME alpha.8.36 version/history synced')
