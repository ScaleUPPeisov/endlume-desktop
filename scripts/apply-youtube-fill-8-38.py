from pathlib import Path


def must(cond, msg):
    if not cond:
        raise SystemExit(f"8.38: {msg}")

p=Path('src-tauri/src/render.rs')
r=p.read_text(encoding='utf-8')
old='fn base_filter(s:&RenderSettings,label:&str)->String{format!("[{label}]scale={}:{}:force_original_aspect_ratio=decrease:flags=lanczos+accurate_rnd,pad={}:{}:(ow-iw)/2:(oh-ih)/2,fps={},setsar=1",s.width,s.height,s.width,s.height,s.fps)}'
new='fn base_filter(s:&RenderSettings,label:&str)->String{format!("[{label}]scale={}:{}:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop={}:{}:(iw-ow)/2:(ih-oh)/2,fps={},setsar=1",s.width,s.height,s.width,s.height,s.fps)}'
if old in r:
    r=r.replace(old,new,1)
elif new not in r:
    raise SystemExit('8.38: base_filter marker missing')
must('force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop=' in r,'YouTube fill/crop filter missing')
must('fn base_filter' in r,'base_filter missing')
p.write_text(r,encoding='utf-8')

p=Path('src/pages/ProjectPage.tsx')
s=p.read_text(encoding='utf-8')
old_text='Для проекта с 1 изображением Fidelity Lock выводит строго 1920×1080 и сохраняет совместимые MP3 bitstream-copy без повторного кодирования.'
new_text='YouTube Fill 16:9: one-image проект всегда заполняет весь кадр 1920×1080 без чёрных полос. Если исходник не 16:9, края слегка обрезаются по центру. Совместимые MP3 идут bitstream-copy без повторного кодирования.'
if old_text in s:
    s=s.replace(old_text,new_text,1)
elif 'YouTube Fill 16:9:' not in s:
    # Keep this patch resilient to wording changes: update the first Fidelity Lock explanatory sentence.
    marker='Для проекта с 1 изображением'
    idx=s.find(marker)
    if idx>=0:
        end=s.find('</p>',idx)
        if end>=0:
            start=s.rfind('>',0,idx)+1
            s=s[:start]+new_text+s[end:]
p.write_text(s,encoding='utf-8')

print('ENDLUME alpha.8.38 YouTube Fill 16:9 / No Black Bars applied')
