from pathlib import Path
import re

version='1.0.0-alpha.8.33'

for file_name in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

for file_name in ['src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

p=Path('src/components/ReleaseHistory.tsx')
h=p.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.33',date:'27.08.2026',current:true,title:'SSD Fast Fidelity + Effects/Subscribe Fix',items:[
    'Исправлена ошибка Live Preview Invalid PNG signature 0x516070020000: ENDLUME теперь игнорирует служебные macOS AppleDouble-файлы ._*, которые появляются на внешних SSD.',
    'Тяжёлый render-work для проекта создаётся на выбранном диске результата. При сохранении на TOSHIBA SSD внутренний диск Mac больше не используется под многогигабайтные промежуточные видео.',
    'Для проекта «1 изображение + Effects + Subscribe» первый проход использует аппаратный HEVC VideoToolbox; libx265 CRF14 остаётся автоматическим quality fallback.',
    'Effects и Subscribe в Smart Fidelity компонуются прямо из исходных файлов без огромного qtrle-cache на внутреннем диске и без лишнего поколения перекодирования.',
    'Длина короткого master подстраивается под длительность непрерывного Effect, чтобы не обрывать 28-секундный эффект на произвольных 30 секундах.',
    'Повторяющиеся Subscribe-композиты переиспользуются, а финальный Smart Fidelity mux читает concat-сегменты напрямую — убрана одна полная дополнительная копия двухчасовой видеодорожки.',
    'Noise 1 и Noise 2 полностью удалены из UI, TypeScript, Rust settings и render filter.',
    'Кроссфейд, Original Audio MP3 bitstream-copy, lossless ALAC fallback, очередь и in-app updater сохранены без изменения логики.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.33'" not in h:
    if marker not in h:raise SystemExit('8.33: release history marker missing')
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')

print('ENDLUME alpha.8.33 version synced')
