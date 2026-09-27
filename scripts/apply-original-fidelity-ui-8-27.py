from pathlib import Path
import re

version='1.0.0-alpha.8.27'
date='25.08.2026'

for file_name in ['src/tauri.ts','src/pages/SettingsPage.tsx']:
    p=Path(file_name); text=p.read_text(encoding='utf-8')
    text=re.sub(r'1\.0\.0-alpha\.8\.\d+',version,text)
    if file_name.endswith('SettingsPage.tsx'):
        text=text.replace('Smart Repeat автоматически ускоряет проекты «1 изображение + музыка + Effects/Subscribe». Локальный builder проверяет этот режим перед установкой.',
                          'Original Fidelity: для проекта «1 изображение + музыка + Effects/Subscribe» ENDLUME сохраняет совместимые MP3 без повторного кодирования и больше не душит видео низким битрейтом.')
    p.write_text(text,encoding='utf-8')

types=Path('src/types.ts')
t=types.read_text(encoding='utf-8')
marker='  targetVideoKbps?: number;\n'
extra='  originalFidelity?: boolean;\n  audioOriginal?: boolean;\n  audioLossless?: boolean;\n'
if extra.strip() not in t:
    if marker not in t: raise SystemExit('8.27 UI: RenderProject marker not found')
    t=t.replace(marker,marker+extra,1)
types.write_text(t,encoding='utf-8')

project=Path('src/pages/ProjectPage.tsx')
x=project.read_text(encoding='utf-8')
old_bitrate='<div className="bigControl"><div><b>Битрейт</b><small>Для видео/эффектов. У проектов с одной картинкой Smart Size автоматически уменьшает размер без повторного многочасового кодирования.</small></div><div className="bigValue">{settings.bitrateMbps} Мбит/с</div><Range value={settings.bitrateMbps} min={1} max={100} onChange={v=>patchSettings({bitrateMbps:v})} minLabel="1 Мбит/с" maxLabel="100 Мбит/с"/></div>'
new_bitrate='''<div style={{margin:"4px 0 18px",padding:"14px 16px",border:"1px solid #33405f",borderRadius:12,background:"rgba(83,94,255,.07)"}}><b style={{display:"block",fontSize:12,color:"#eaf0ff",marginBottom:5}}>ORIGINAL FIDELITY</b><small style={{display:"block",lineHeight:1.55,color:"#98a3c3"}}>Для проекта с одной картинкой ENDLUME ставит качество выше размера: Effects/Subscribe кэшируются без потери RGB, видео кодируется quality-first через HEVC VideoToolbox, а совместимые MP3 копируются в итог без повторного аудиокодирования. 700–1000 МБ — только если это достигается без заметной потери качества.</small></div><div className="bigControl"><div><b>Битрейт</b><small>Для обычных видео-проектов. В Original Fidelity этот лимит не используется для принудительного ухудшения картинки или Effects.</small></div><div className="bigValue">{settings.bitrateMbps} Мбит/с</div><Range value={settings.bitrateMbps} min={1} max={100} onChange={v=>patchSettings({bitrateMbps:v})} minLabel="1 Мбит/с" maxLabel="100 Мбит/с"/></div>'''
if old_bitrate in x:
    x=x.replace(old_bitrate,new_bitrate,1)
elif 'ORIGINAL FIDELITY' not in x:
    raise SystemExit('8.27 UI: bitrate block not found')

old_cross='<div className="bigControl compactControl"><div><b>Кроссфейд между треками</b><small>Плавный переход без резкого стыка</small></div><div className="bigValue small">{settings.crossfadeSec} сек</div><Range value={settings.crossfadeSec} min={1} max={10} onChange={v=>patchSettings({crossfadeSec:v})} minLabel="1 сек" maxLabel="10 сек"/></div>'
new_cross='<div className="bigControl compactControl"><div><b>Кроссфейд между треками</b><small>В Original Fidelity автоматически отключается: иначе исходные MP3 пришлось бы декодировать и заново сжимать. Для обычных видео можно использовать значение ниже.</small></div><div className="bigValue small">{settings.crossfadeSec} сек</div><Range value={settings.crossfadeSec} min={0} max={10} onChange={v=>patchSettings({crossfadeSec:v})} minLabel="0 сек" maxLabel="10 сек"/></div>'
if old_cross in x:
    x=x.replace(old_cross,new_cross,1)
project.write_text(x,encoding='utf-8')

render=Path('src/pages/RenderPage.tsx')
r=render.read_text(encoding='utf-8')
old='{active.smartSize&&<span className="smartSizeLine">Smart Size: статичное изображение • цель ≈ 1.0–1.2 ГБ / 2 ч • video ≈ {((active.targetVideoKbps||850)/1000).toFixed(2)} Мбит/с • audio 320 кбит/с</span>}'
new='{active.originalFidelity?<span className="smartSizeLine">Original Fidelity: quality-first HEVC • аудио {active.audioOriginal?"MP3 bitstream-copy без перекодирования":active.audioLossless?"ALAC lossless fallback":"проверяется"} • размер не уменьшается ценой качества</span>:active.smartSize&&<span className="smartSizeLine">Smart Size: статичное изображение</span>}'
if old in r:
    r=r.replace(old,new,1)
elif 'Original Fidelity: quality-first HEVC' not in r:
    raise SystemExit('8.27 UI: RenderPage Smart Size line not found')
render.write_text(r,encoding='utf-8')

history=Path('src/components/ReleaseHistory.tsx')
h=history.read_text(encoding='utf-8')
h=h.replace('current:true,','current:false,')
entry='''  {version:'1.0.0-alpha.8.27',date:'25.08.2026',current:true,title:'Original Fidelity: музыка без повторного lossy-кодирования + quality-first видео',items:[
    'Для проектов «1 изображение + музыка + Effects/Subscribe» включён Original Fidelity.',
    'Совместимые MP3 с одинаковыми sample rate/channel layout объединяются через stream-copy: аудиокадры не перекодируются.',
    'Кроссфейд, LUFS-нормализация и ambient автоматически не применяются в Original Fidelity, потому что любая такая обработка требует изменения исходного аудиосигнала.',
    'Если MP3 нельзя безопасно stream-copy объединить, ENDLUME использует ALAC lossless fallback вместо AAC; файл может стать больше 1 ГБ.',
    'Убран жёсткий 520–700 кбит/с лимит для Smart Repeat: изображение и Effects больше не портятся ради размера.',
    'На Apple Silicon Original Fidelity использует HEVC VideoToolbox quality-first; software fallback — x265 CRF 14.',
    'Effects/Subscribe по-прежнему композятся из lossless qtrle chromakey-cache и сохраняют исходное соотношение сторон.',
    '20–30 секунд остаются архитектурной целью для короткого master + stream-copy mux, но качество имеет приоритет над обещанием размера или времени.'
  ]},
'''
marker='const releases:Release[]=[\n'
if "version:'1.0.0-alpha.8.27'" not in h:
    if marker not in h: raise SystemExit('8.27 UI: history marker not found')
    h=h.replace(marker,marker+entry,1)
history.write_text(h,encoding='utf-8')

print('ENDLUME alpha.8.27 UI/version patch applied')
