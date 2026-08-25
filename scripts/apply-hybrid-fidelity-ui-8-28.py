from pathlib import Path
import re

version='1.0.0-alpha.8.28'

for file_name in ['src/tauri.ts','src/pages/SettingsPage.tsx']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    if file_name.endswith('SettingsPage.tsx'):
        text=text.replace('Original Fidelity: для проекта «1 изображение + музыка + Effects/Subscribe» ENDLUME сохраняет совместимые MP3 без повторного кодирования и больше не душит видео низким битрейтом.',
                          'Hybrid Fidelity 8.28: короткий x265 master повторяется через stream-copy, совместимые MP3 сохраняются без аудиоперекодирования и упаковываются в QuickTime MOV для корректного звука на Mac.')
    p.write_text(text,encoding='utf-8')

project=Path('src/pages/ProjectPage.tsx')
x=project.read_text(encoding='utf-8')
x=x.replace('Для проекта с одной картинкой ENDLUME ставит качество выше размера: Effects/Subscribe кэшируются без потери RGB, видео кодируется quality-first через HEVC VideoToolbox, а совместимые MP3 копируются в итог без повторного аудиокодирования. 700–1000 МБ — только если это достигается без заметной потери качества.',
'''Для проекта с одной картинкой ENDLUME использует Hybrid Fidelity: исходное изображение не пережимается заранее, Effects/Subscribe берутся из lossless-cache и один раз кодируются в короткий HEVC/x265 master CRF14. Дальше двухчасовое видео собирается stream-copy. Совместимые MP3 проходят bitstream-copy с исправлением таймстампов и сохраняются в QuickTime MOV без повторного lossy-кодирования. Цель размера — примерно 700–1000 МБ, когда сцена достаточно статична; качество не режется жёстким низким битрейтом.''')
project.write_text(x,encoding='utf-8')

render=Path('src/pages/RenderPage.tsx')
r=render.read_text(encoding='utf-8')
r=r.replace('Original Fidelity: quality-first HEVC • аудио {active.audioOriginal?"MP3 bitstream-copy без перекодирования":active.audioLossless?"ALAC lossless fallback":"проверяется"} • размер не уменьшается ценой качества',
'''Hybrid Fidelity: short-master x265 CRF14 + stream-copy • аудио {active.audioOriginal?"MP3 bitstream-copy + исправленные таймстампы":active.audioLossless?"ALAC lossless fallback":"проверяется"} • QuickTime MOV • цель ≈ 0.7–1.0 ГБ при статичной сцене''')
render.write_text(r,encoding='utf-8')

history=Path('src/components/ReleaseHistory.tsx')
h=history.read_text(encoding='utf-8')
h=h.replace('current:true,','current:false,')
entry='''  {version:'1.0.0-alpha.8.28',date:'26.08.2026',current:true,title:'Hybrid Fidelity: маленький файл + живой MP3 + короткий master',items:[
    'Исправлена причина файла 14–17 ГБ: VideoToolbox q95 больше не кодирует весь повторяющийся визуальный master с огромным средним битрейтом.',
    'Для проекта «1 изображение + музыка + Effects/Subscribe» исходная картинка идёт напрямую в короткий 30-секундный x265 CRF14 master без предварительного пережатия.',
    'Короткий master повторяется через stream-copy; статичные пиксели и небольшие Effects хорошо сжимаются, поэтому двухчасовой проект больше не обязан занимать десятки гигабайт.',
    'Effects и Subscribe продолжают использовать lossless qtrle chromakey-cache, сохраняют aspect ratio и кодируются только в коротких сегментах/master.',
    'Совместимые MP3 сначала очищаются stream-copy от ID3/Xing, затем объединяются как непрерывный MP3-поток с новыми монотонными таймстампами. Аудиосэмплы не перекодируются.',
    'Original Fidelity теперь сохраняется в QuickTime MOV: это устраняет сценарий, когда MP3-трек присутствует в MP4, но QuickTime Player воспроизводит видео без звука.',
    'Перед успешным рендером ENDLUME не только видит аудиотрек через FFprobe, но и реально декодирует его тестовый фрагмент.',
    'Если MP3 имеют несовместимые параметры, остаётся ALAC lossless fallback вместо AAC.'
  ]},
'''
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.28'" not in h:
    if marker not in h: raise SystemExit('8.28 UI: history marker missing')
    h=h.replace(marker,marker+entry,1)
history.write_text(h,encoding='utf-8')

print('ENDLUME alpha.8.28 UI/version patch applied')
