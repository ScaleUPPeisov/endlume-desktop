from pathlib import Path

p=Path('src-tauri/src/render.rs')
r=p.read_text(encoding='utf-8')

helper="""fn chroma_despill_type(hex:&str)->&'static str{
  let raw=hex.trim().trim_start_matches('#');
  if raw.len()==6{if let Ok(v)=u32::from_str_radix(raw,16){let g=(v>>8)&255;let b=v&255;if b>g{return \"blue\"}}}
  \"green\"
}
"""

# Insert helper by function boundary, not by an exact historical whole-line literal.
if 'fn chroma_despill_type(' not in r:
    lines=r.splitlines(keepends=True)
    inserted=False
    out=[]
    for line in lines:
        out.append(line)
        if not inserted and line.lstrip().startswith('fn color_ffmpeg('):
            out.append(helper)
            inserted=True
    if not inserted:
        raise SystemExit('8.39 chroma repair: color_ffmpeg function not found')
    r=''.join(out)

# Normalize the actual direct-render chromakey format structurally. Previous
# releases may wrap this expression in different else/if formatting, so never
# match the entire historical line.
lines=r.splitlines(keepends=True)
found=0
changed=0
out=[]
for line in lines:
    if 'chromakey=' in line and 'color_ffmpeg(&e.key_color)' in line:
        found+=1
        if 'despill=type=' not in line:
            if 'chromakey={}:{}:{}' not in line:
                raise SystemExit('8.39 chroma repair: chromakey placeholders changed unexpectedly')
            line=line.replace(
                'chromakey={}:{}:{}',
                'chromakey={}:{}:{},despill=type={}:mix={}:expand=0.20',
                1,
            )
            needle='e.blend)'
            replacement='e.blend,chroma_despill_type(&e.key_color),e.despill.clamp(0.0,1.0))'
            if needle not in line:
                raise SystemExit('8.39 chroma repair: chromakey blend argument not found')
            line=line.replace(needle,replacement,1)
            changed+=1
    out.append(line)
r=''.join(out)

if found < 1:
    raise SystemExit('8.39 chroma repair: no direct-render chromakey expression found')
if 'despill=type={}:mix={}:expand=0.20' not in r:
    raise SystemExit('8.39 chroma repair: despill filter missing after normalization')
if 'chroma_despill_type(&e.key_color),e.despill.clamp(0.0,1.0)' not in r:
    raise SystemExit('8.39 chroma repair: despill arguments missing after normalization')
if 'fn chroma_despill_type(' not in r:
    raise SystemExit('8.39 chroma repair: helper missing')

p.write_text(r,encoding='utf-8')
print(f'ENDLUME: 8.39 render chroma normalized; expressions={found}, changed={changed}')
