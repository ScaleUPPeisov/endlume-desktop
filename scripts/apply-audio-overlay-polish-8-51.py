#!/usr/bin/env python3
from pathlib import Path
import re,sys

ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd()

def need(rel):
    p=ROOT/rel
    if not p.is_file(): raise SystemExit(f'8.51 polish: missing {rel}')
    return p

def must(cond,msg):
    if not cond: raise SystemExit('8.51 polish: '+msg)

# ---------------------------------------------------------------------------
# 1. One-image music videos NEVER cut the song at the nominal 2h boundary.
# The existing 8.49 whole-track math already finds the end of the current song;
# make that policy mandatory for the one-image ENDLUME product shape even if an
# old persisted UI setting still says "exact".
# ---------------------------------------------------------------------------
p=need('src-tauri/src/render.rs')
s=p.read_text(encoding='utf-8')
old='let target=job.settings.duration_hours*3600.0;let final_duration=smart_final_duration(target,&durations,job.settings.crossfade_sec,&job.settings.duration_mode);let audio='
new='let target=job.settings.duration_hours*3600.0;let duration_mode=if smart_repeat_project(job){"whole-track"}else{job.settings.duration_mode.as_str()};let final_duration=smart_final_duration(target,&durations,job.settings.crossfade_sec,duration_mode);let audio='
must(old in s or 'let duration_mode=if smart_repeat_project(job){"whole-track"}' in s,'render duration call not found')
if old in s:s=s.replace(old,new,1)
must('let duration_mode=if smart_repeat_project(job){"whole-track"}else{job.settings.duration_mode.as_str()};' in s,'mandatory one-image whole-track policy missing')
must('if t-target<=240.0{t}else{target}' not in s,'legacy 4-minute song cut cap returned')
p.write_text(s,encoding='utf-8')

# ---------------------------------------------------------------------------
# 2. Stop destroying user saturation on every library save. Keep sane bounds.
# 8.41 already owns the despill migration; preserve it.
# ---------------------------------------------------------------------------
p=need('src-tauri/src/persistence.rs')
s=p.read_text(encoding='utf-8')
old='if obj.get("saturation").and_then(Value::as_f64).unwrap_or(1.0)!=1.0{obj.insert("saturation".into(),json!(1.0));changed=true;}'
new='let saturation=obj.get("saturation").and_then(Value::as_f64).unwrap_or(1.25);if !saturation.is_finite()||saturation<0.50||saturation>2.0{obj.insert("saturation".into(),json!(1.25));changed=true;}'
must(old in s or 'saturation<0.50||saturation>2.0' in s,'legacy saturation reset not found')
if old in s:s=s.replace(old,new,1)
must('json!(1.0));changed=true;' not in s or 'saturation' not in s[s.find('json!(1.0));changed=true;')-120:s.find('json!(1.0));changed=true;')+80],'saturation is still forcibly reset to 1.0')
must('saturation<0.50||saturation>2.0' in s,'saturation bounds missing')
p.write_text(s,encoding='utf-8')

# ---------------------------------------------------------------------------
# 3. FFmpeg Effects/Subscribe cache: actually apply saturation plus a restrained
# punch and stronger alpha. This targets the washed-out Subscribe/equalizer look
# without touching the base image/video.
# ---------------------------------------------------------------------------
p=need('src-tauri/src/cache.rs')
s=p.read_text(encoding='utf-8')
anchor='let similarity=e.similarity.clamp(0.001,0.60);let blend=e.blend.clamp(0.001,0.35);\n    let motion='
if anchor in s:
    s=s.replace(anchor,'let similarity=e.similarity.clamp(0.001,0.60);let blend=e.blend.clamp(0.001,0.35);let sat=e.saturation.clamp(0.50,2.0);\n    let motion=',1)
must('let sat=e.saturation.clamp(0.50,2.0);' in s,'render saturation scalar missing')
old_luma='"luma"=>format!("{motion},format=rgba,lumakey=threshold={}:tolerance={}:softness=0.08,format=argb",e.luma_threshold,e.luma_tolerance),'
new_luma='"luma"=>format!("{motion},format=rgba,lumakey=threshold={}:tolerance={}:softness=0.08,colorchannelmixer=aa=1.25,format=yuva444p,eq=contrast=1.10:brightness=0.015:saturation={sat},format=argb",e.luma_threshold,e.luma_tolerance),'
if old_luma in s:s=s.replace(old_luma,new_luma,1)
old_screen='"screen"=>format!("{motion},format=rgb24"),'
new_screen='"screen"=>format!("{motion},format=yuv444p,eq=contrast=1.12:brightness=0.020:saturation={sat},format=rgb24"),'
if old_screen in s:s=s.replace(old_screen,new_screen,1)
old_chroma='_=>format!("{motion},format=rgba,colorkey={}:{}:{},despill=type={}:mix={}:expand=0.20,format=argb",color(&e.key_color),similarity,blend,despill_type(&e.key_color),e.despill.clamp(0.0,1.0))'
new_chroma='_=>format!("{motion},format=rgba,colorkey={}:{}:{},despill=type={}:mix={}:expand=0.20,colorchannelmixer=aa=1.25,format=yuva444p,eq=contrast=1.10:brightness=0.015:saturation={sat},format=argb",color(&e.key_color),similarity,blend,despill_type(&e.key_color),e.despill.clamp(0.0,1.0))'
if old_chroma in s:s=s.replace(old_chroma,new_chroma,1)
for marker in ['colorchannelmixer=aa=1.25','eq=contrast=1.10:brightness=0.015:saturation={sat}','eq=contrast=1.12:brightness=0.020:saturation={sat}']:
    must(marker in s,'cache vivid marker missing: '+marker)
p.write_text(s,encoding='utf-8')

# ---------------------------------------------------------------------------
# 4. Live WebGL Preview must match final render. Add saturation + punch + alpha,
# while preserving the existing 8.41 despill shader.
# ---------------------------------------------------------------------------
p=need('src/components/LiveCompositePreview.tsx')
s=p.read_text(encoding='utf-8')
s=s.replace('uniform float dsp;uniform float mode;','uniform float dsp;uniform float sat;uniform float mode;',1)
s=s.replace('gl_FragColor=vec4(c,a);}`);','float lum=dot(c,vec3(.2126,.7152,.0722));c=mix(vec3(lum),c,sat);c=clamp((c-.5)*1.10+.515,0.,1.);a=min(1.,a*1.25);gl_FragColor=vec4(c,a);}`);',1)
s=s.replace("uDsp=gl.getUniformLocation(program,'dsp'),uMode=","uDsp=gl.getUniformLocation(program,'dsp'),uSat=gl.getUniformLocation(program,'sat'),uMode=",1)
s=s.replace('gl.uniform1f(uDsp,Math.max(0,Math.min(1,e.despill||0)));gl.uniform1f(uMode','gl.uniform1f(uDsp,Math.max(0,Math.min(1,e.despill||0)));gl.uniform1f(uSat,Math.max(.5,Math.min(2,e.saturation||1.25)));gl.uniform1f(uMode',1)
for marker in ['uniform float sat','uSat=gl.getUniformLocation','gl.uniform1f(uSat','a=min(1.,a*1.25)']:
    must(marker in s,'Live Preview vivid marker missing: '+marker)
p.write_text(s,encoding='utf-8')

# ---------------------------------------------------------------------------
# 5. Editor: defaults are vivid and both Effects + Subscribe expose saturation.
# ---------------------------------------------------------------------------
p=need('src/pages/Editors.tsx')
s=p.read_text(encoding='utf-8')
s=re.sub(r'saturation:\s*1(?=\s*[,}])','saturation: 1.25',s)
blend='<SmallRange label="Blend / мягкость края" value={current.blend} min={0.001} max={0.35} step={0.001} onChange={(value) => patch({ blend: value })} />'
sat='<SmallRange label="Насыщенность / сила цвета" value={current.saturation} min={0.5} max={2} step={0.05} onChange={(value) => patch({ saturation: value })} />'
if 'Насыщенность / сила цвета' not in s:
    count=s.count(blend)
    must(count>=2,f'expected Effects + Subscribe Blend controls, got {count}')
    s=s.replace(blend,blend+'\n            '+sat)
must(s.count('Насыщенность / сила цвета')>=2,'Effects/Subscribe saturation controls missing')
must(s.count('saturation: 1.25')>=2,'vivid defaults missing')
p.write_text(s,encoding='utf-8')

# 6. In-memory load migration makes existing neutral legacy presets vivid now,
# without waiting for the user to recreate them.
p=need('src/store.ts')
s=p.read_text(encoding='utf-8')
old='...e,despill:e.despill>0?e.despill:0.35'
new='...e,saturation:Math.abs((e.saturation??1)-1)<0.001?1.25:(e.saturation??1),despill:e.despill>0?e.despill:0.35'
if old in s:s=s.replace(old,new)
must(s.count('saturation:Math.abs((e.saturation??1)-1)<0.001?1.25')>=2,'legacy library vivid migration missing')
p.write_text(s,encoding='utf-8')

print('ENDLUME 8.51 audio boundary + vivid Effects/Subscribe polish: PASS')
