from pathlib import Path
import re

version='1.0.0-alpha.8.31'

for file_name in ['src-tauri/Cargo.toml','src-tauri/tauri.conf.json']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

for file_name in ['src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/RenderPage.tsx','src/pages/ProjectPage.tsx']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

p=Path('src/components/ReleaseHistory.tsx')
h=p.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.31',date:'26.08.2026',current:true,title:'Render Center Live + рабочий lossless crossfade + встроенный Шум 1/2',items:[
    'Render Center теперь всегда показывает фактический текущий этап и процент, даже если backend использует новый Hybrid Fidelity stage.',
    'Кроссфейд в статичных проектах больше не игнорируется: переход реально строится через acrossfade.',
    'После кроссфейда музыка сохраняется в ALAC lossless, поэтому нет повторного AAC/MP3 lossy-сжатия. При выключенном кроссфейде совместимые MP3 остаются bitstream-copy.',
    'Добавлены встроенные эффекты «Шум 1» и «Шум 2» с отдельным ВКЛ/ВЫКЛ; внешний overlay-файл не нужен.',
    'Большой служебный блок ORIGINAL/HYBRID FIDELITY удалён из основного интерфейса.',
    'Сохранены fresh-clone builder, Effects/Subscribe gates, 4K SSIM gate, compact short-master и atomic install/rollback.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.31'" not in h:
    if marker not in h: raise SystemExit('8.31: release history marker missing')
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')
print('ENDLUME alpha.8.31 version/UI sync applied')