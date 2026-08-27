from pathlib import Path
import re, subprocess, shutil

version = "1.0.0-alpha.8.34"

for file_name in ["package.json","src-tauri/Cargo.toml","src-tauri/tauri.conf.json"]:
    p=Path(file_name); text=p.read_text(encoding="utf-8")
    text=re.sub(r"1\.0\.0-alpha\.8\.\d+",version,text)
    p.write_text(text,encoding="utf-8")

for file_name in ["src/tauri.ts","src/pages/SettingsPage.tsx","src/pages/App.tsx"]:
    p=Path(file_name); text=p.read_text(encoding="utf-8")
    text=re.sub(r"1\.0\.0-alpha\.8\.\d+",version,text)
    p.write_text(text,encoding="utf-8")

# Restore the earlier approved transparent gradient infinity icon, not the
# black rounded-square Dock tile.
icons=Path("src-tauri/icons"); icons.mkdir(parents=True,exist_ok=True)
master=icons/"icon.png"
generator=Path("scripts/generate-icon-8-32.swift")
if not generator.is_file():
    raise SystemExit("8.34: original ENDLUME icon generator missing")
subprocess.run(["/usr/bin/swift",str(generator),str(master)],check=True)

def resize(src:Path,dst:Path,size:int):
    subprocess.run(["/usr/bin/sips","-z",str(size),str(size),str(src),"--out",str(dst)],check=True,stdout=subprocess.DEVNULL)

resize(master,icons/"32x32.png",32)
resize(master,icons/"128x128.png",128)
resize(master,icons/"128x128@2x.png",256)
iconset=icons/"ENDLUME.iconset"
if iconset.exists(): shutil.rmtree(iconset)
iconset.mkdir()
for name,size in [
    ("icon_16x16.png",16),("icon_16x16@2x.png",32),
    ("icon_32x32.png",32),("icon_32x32@2x.png",64),
    ("icon_128x128.png",128),("icon_128x128@2x.png",256),
    ("icon_256x256.png",256),("icon_256x256@2x.png",512),
    ("icon_512x512.png",512),("icon_512x512@2x.png",1024),
]:
    resize(master,iconset/name,size)
subprocess.run(["/usr/bin/iconutil","-c","icns",str(iconset),"-o",str(icons/"icon.icns")],check=True)
shutil.rmtree(iconset,ignore_errors=True)

p=Path("src/components/ReleaseHistory.tsx")
h=p.read_text(encoding="utf-8").replace("current:true,","current:false,")
entry="""  {version:'1.0.0-alpha.8.34',date:'27.08.2026',current:true,title:'Preview Shield + 100/100 Stability Gate',items:[
    'Effects и Subscribe: кроме ._* ENDLUME теперь проверяет AppleDouble/resource-fork по сигнатуре файла, поэтому даже переименованный служебный файл не попадёт в FFmpeg.',
    'Live Preview cache переведён на v6, чтобы старые повреждённые preview-файлы не переиспользовались.',
    'Импорт Effects/Subscribe блокирует служебные macOS-файлы до копирования в постоянную библиотеку.',
    'Noise 1 и Noise 2 остаются полностью удалёнными.',
    'Сохранён Fast Fidelity: Apple HEVC VideoToolbox first, libx265 fallback, короткий master, повторное использование Subscribe и direct concat.',
    'Целевой профиль 1 изображение + 10–15 треков + 2 часа сохранён: 700–1000 МБ при типичном 320 кбит/с MP3 и компактном HEVC budget.',
    'Оригинальный MP3 идёт bitstream-copy; при реальном crossfade используется lossless ALAC.',
    'Возвращена прежняя прозрачная ENDLUME infinity-иконка без чёрного квадратного фона.',
    'Перед установкой выполняется отдельный 100/100 Effects+Subscribe preview stability smoke; при любом сбое старая ENDLUME не заменяется.'
  ]},
"""
marker="const releases:Release[]=[\n"
if "version:'1.0.0-alpha.8.34'" not in h:
    if marker not in h: raise SystemExit("8.34: release history marker missing")
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding="utf-8")

print("ENDLUME alpha.8.34 version + previous icon synced")
