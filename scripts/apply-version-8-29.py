from pathlib import Path
import re

version='1.0.0-alpha.8.29'

# Rust / Tauri versions
for file_name in ['src-tauri/Cargo.toml','src-tauri/tauri.conf.json']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    p.write_text(text,encoding='utf-8')

# Frontend version labels
for file_name in ['src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/RenderPage.tsx','src/pages/ProjectPage.tsx']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    text=text.replace('Hybrid Fidelity: short-master x265 CRF14','Hybrid Fidelity: short-master x265 CRF22')
    text=text.replace('CRF14','CRF22')
    if file_name.endswith('ProjectPage.tsx'):
        text=text.replace('700–1000 МБ — только если это достигается без заметной потери качества.','Цель около 1 ГБ / 2 ч применяется только пока тест качества остаётся в visually-lossless зоне; исходные MP3 не перекодируются.')
    p.write_text(text,encoding='utf-8')

# Release history: keep one current version and add 8.29 entry.
p=Path('src/components/ReleaseHistory.tsx')
h=p.read_text(encoding='utf-8').replace('current:true,','current:false,')
entry="""  {version:'1.0.0-alpha.8.29',date:'26.08.2026',current:true,title:'Stability Gate: ~1 ГБ / 2 ч + exact MP3 + clean install',items:[
    'Исправлен установщик Hybrid Fidelity: больше нет зависимости от точного minified-маркера Subscribe.',
    'Установка идёт только после Python patch preflight, TypeScript, production frontend, Rust и реальных FFmpeg regression-тестов.',
    'Hybrid Fidelity использует короткий HEVC/x265 CRF22 master: на статичном 4K фоне с небольшим движущимся overlay тест качества держит SSIM >= 0.995.',
    'Цель размера для типового проекта «1 картинка + музыка + небольшие Effects/Subscribe» — около 1 ГБ на 2 часа; качество имеет приоритет, поэтому сложный постоянный motion может дать файл больше.',
    'Совместимые MP3 проходят через bitstream-copy без повторного lossy-кодирования; финальный MOV обязан содержать декодируемую аудиодорожку с монотонными DTS.',
    'Исходная картинка не получает отдельного предварительного пережатия: short-master строится напрямую из оригинала и lossless overlay-cache.'
  ]},
"""
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.29'" not in h:
    if marker not in h: raise SystemExit('8.29 UI: release history marker missing')
    h=h.replace(marker,marker+entry,1)
p.write_text(h,encoding='utf-8')

print('ENDLUME alpha.8.29 version/UI sync applied')
