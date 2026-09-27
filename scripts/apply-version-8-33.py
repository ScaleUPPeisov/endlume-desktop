from pathlib import Path
import re,subprocess,shutil

version='1.0.0-alpha.8.33'

for file_name in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

for file_name in ['src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

# Restore the clean ENDLUME infinity icon the user approved earlier: cyan -> violet -> magenta,
# transparent background, no black rounded-square frame.
icons=Path('src-tauri/icons'); icons.mkdir(parents=True,exist_ok=True)
master=icons/'icon.png'
generator=Path('scripts/generate-icon-8-32.swift')
if not generator.is_file(): raise SystemExit('8.33: ENDLUME icon generator missing')
subprocess.run(['/usr/bin/swift',str(generator),str(master)],check=True)
def resize(src:Path,dst:Path,size:int):
    subprocess.run(['/usr/bin/sips','-z',str(size),str(size),str(src),'--out',str(dst)],check=True,stdout=subprocess.DEVNULL)
resize(master,icons/'32x32.png',32)
resize(master,icons/'128x128.png',128)
resize(master,icons/'128x128@2x.png',256)
iconset=icons/'ENDLUME.iconset'
if iconset.exists(): shutil.rmtree(iconset)
iconset.mkdir()
for name,size in [('icon_16x16.png',16),('icon_16x16@2x.png',32),('icon_32x32.png',32),('icon_32x32@2x.png',64),('icon_128x128.png',128),('icon_128x128@2x.png',256),('icon_256x256.png',256),('icon_256x256@2x.png',512),('icon_512x512.png',512),('icon_512x512@2x.png',1024)]:
    resize(master,iconset/name,size)
subprocess.run(['/usr/bin/iconutil','-c','icns',str(iconset),'-o',str(icons/'icon.icns')],check=True)
shutil.rmtree(iconset,ignore_errors=True)

p=Path('src/components/ReleaseHistory.tsx')
h=p.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.33',date:'27.08.2026',current:true,title:'SSD Fast Fidelity + Effects/Subscribe Fix',items:[
    'Исправлена ошибка Live Preview Invalid PNG signature 0x516070020000: ENDLUME теперь игнорирует служебные macOS AppleDouble-файлы ._*, которые появляются на внешних SSD.',
    'Тяжёлый render-work для проекта создаётся на выбранном диске результата. При сохранении на внешний SSD внутренний диск Mac больше не используется под многогигабайтные промежуточные видео.',
    'Для проекта «1 изображение + Effects + Subscribe» первый проход использует аппаратный HEVC VideoToolbox; libx265 CRF14 остаётся автоматическим quality fallback.',
    'Effects и Subscribe в Smart Fidelity компонуются прямо из исходных файлов без огромного qtrle-cache на внутреннем диске и без лишнего поколения перекодирования.',
    'Длина короткого master подстраивается под длительность непрерывного Effect, чтобы не обрывать эффект.',
    'Повторяющиеся Subscribe-композиты переиспользуются, а финальный Smart Fidelity mux читает concat-сегменты напрямую — убрана одна полная дополнительная копия двухчасовой видеодорожки.',
    'Noise 1 и Noise 2 полностью удалены из UI, TypeScript, Rust settings и render filter.',
    'Кроссфейд, Original Audio MP3 bitstream-copy, lossless ALAC fallback, очередь и in-app updater сохранены.',
    'Возвращена фирменная ENDLUME infinity-иконка без чёрной квадратной рамки.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.33'" not in h:
    if marker not in h:raise SystemExit('8.33: release history marker missing')
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')

print('ENDLUME alpha.8.33 version + original icon synced')
