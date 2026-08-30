from pathlib import Path

p=Path('src-tauri/src/render.rs')
r=p.read_text(encoding='utf-8')

helper="""fn chroma_despill_type(hex:&str)->&'static str{
  let raw=hex.trim().trim_start_matches('#');
  if raw.len()==6{if let Ok(v)=u32::from_str_radix(raw,16){let g=(v>>8)&255;let b=v&255;if b>g{return \"blue\"}}}
  \"green\"
}
"""
color_marker='fn color_ffmpeg(hex:&str)->String{format!("0x{}",hex.trim().trim_start_matches(\'#\').trim_start_matches("0x"))}\n'
if 'fn chroma_despill_type(' not in r:
    if color_marker not in r:
        raise SystemExit('8.39 chroma repair: color_ffmpeg marker missing')
    r=r.replace(color_marker,color_marker+helper,1)

old='else{format!("[{idx}:v]fps={},format=rgba,chromakey={}:{}:{}",s.fps,color_ffmpeg(&e.key_color),e.similarity.max(0.00001),e.blend)}'
new='else{format!("[{idx}:v]fps={},format=rgba,chromakey={}:{}:{},despill=type={}:mix={}:expand=0.20",s.fps,color_ffmpeg(&e.key_color),e.similarity.max(0.00001),e.blend,chroma_despill_type(&e.key_color),e.despill.clamp(0.0,1.0))}'
if old in r:
    r=r.replace(old,new,1)
else:
    old2='format!("[{idx}:v]fps={},format=rgba,chromakey={}:{}:{}",s.fps,color_ffmpeg(&e.key_color),e.similarity.max(0.00001),e.blend)'
    new2='format!("[{idx}:v]fps={},format=rgba,chromakey={}:{}:{},despill=type={}:mix={}:expand=0.20",s.fps,color_ffmpeg(&e.key_color),e.similarity.max(0.00001),e.blend,chroma_despill_type(&e.key_color),e.despill.clamp(0.0,1.0))'
    if old2 in r:
        r=r.replace(old2,new2,1)

if 'despill=type={}:mix={}:expand=0.20' not in r:
    raise SystemExit('8.39 chroma repair: render chromakey fragment still not normalized')
if 'fn chroma_despill_type(' not in r:
    raise SystemExit('8.39 chroma repair: helper missing')

p.write_text(r,encoding='utf-8')
print('ENDLUME: 8.39 render chroma marker normalized')
