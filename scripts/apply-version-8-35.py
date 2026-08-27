from pathlib import Path
import re

version='1.0.0-alpha.8.35'

for file_name in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

p=Path('src/components/ReleaseHistory.tsx')
h=p.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.35',date:'27.08.2026',current:true,title:'Strict Fidelity • 1-minute target',items:[
    'Для проекта 1 изображение + музыка Smart Repeat рендерится максимум в 30 FPS: статичная картинка не теряет деталей, а нагрузка Effects/Subscribe снижается примерно вдвое относительно старого 60 FPS профиля.',
    'Убран двухсекундный GOP, который создавал слишком много тяжёлых 4K I-кадров. Теперь один GOP покрывает полный short-master, а VideoToolbox получает увеличенный 64 MB buffer для чистого первого кадра.',
    '4K video budget настроен на 780 кбит/с; вместе с типичным оригинальным MP3 320 кбит/с расчётный двухчасовой файл около 0.99 GB.',
    'Strict Fidelity отключает crossfade/LUFS/ambient только для one-image профиля, чтобы музыка шла точным MP3 bitstream-copy без повторного lossy-кодирования и без многогигабайтного ALAC.',
    'Если исходные аудиофайлы невозможно объединить точным MP3 copy, ENDLUME теперь показывает понятную ошибку вместо скрытого перехода на большой ALAC-файл.',
    'Новые настройки по умолчанию: 4K, HEVC, 30 FPS, crossfade выключен. Старый сохранённый 4K60/crossfade=3 профиль мигрирует один раз.',
    'AppleDouble Preview Shield, Live Preview v6, удаление Noise 1/2, предыдущая ENDLUME infinity-иконка и все queue/updater исправления сохранены.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.35'" not in h:
    if marker not in h: raise SystemExit('8.35: release history marker missing')
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')

print('ENDLUME alpha.8.35 version/history synced')
