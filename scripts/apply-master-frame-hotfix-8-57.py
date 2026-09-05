#!/usr/bin/env python3
from pathlib import Path
import json,re

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'src-tauri/src/render.rs'
s=R.read_text()

def once(text,old,new,label):
    n=text.count(old)
    if n!=1: raise SystemExit(f'8.57 migration: {label}: expected 1 anchor, found {n}')
    return text.replace(old,new,1)

# Root cause of 2048/3381: the cached keyed Effect overlay used shortest=1.
# The first shorter Effect therefore ended the entire visual chain before the
# natural 56.355s cycle had completed. Keep the base timeline alive and let
# -stream_loop -1 repeat the cached Effect normally.
old='graph.push_str(&format!(";[{idx}:v]fps={},format=argb[{fx}];[{base}][{fx}]overlay=x=\'{x}\':y=\'{y}\':shortest=1:eof_action=repeat:format=auto[{next}]",s.fps));base=next;continue'
new='graph.push_str(&format!(";[{idx}:v]fps={},setpts=PTS-STARTPTS,format=argb[{fx}];[{base}][{fx}]overlay=x=\'{x}\':y=\'{y}\':shortest=0:repeatlast=1:eof_action=repeat:format=auto[{next}]",s.fps));base=next;continue'
s=once(s,old,new,'strict-prealpha lifetime')

# Do not silently accept a truncated master. The exact frame assertion stays.
s=s.replace('Strict 8.56 master: {got} кадров вместо {master_frames}','Strict 8.57 master: {got} кадров вместо {master_frames}')
s=s.replace('Strict 8.56: fidelity master полного Effects-цикла','Strict 8.57: fidelity master полного Effects-цикла')
s=s.replace('Strict 8.56 zero-copy готов','Strict 8.57 zero-copy готов')
R.write_text(s)

# Version only. No VYRON/UI/store/cache behavior changes in this hotfix.
for rel in ['package.json','src-tauri/tauri.conf.json']:
    p=ROOT/rel;d=json.loads(p.read_text());d['version']='1.0.0-alpha.8.57';p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
p=ROOT/'src-tauri/Cargo.toml';txt=p.read_text();txt,n=re.subn(r'(?m)^version\s*=\s*"1\.0\.0-alpha\.8\.56"$', 'version = "1.0.0-alpha.8.57"',txt,count=1)
if n!=1: raise SystemExit('8.57 migration: Cargo version anchor missing')
p.write_text(txt)
p=ROOT/'package-lock.json'
if p.exists():
    d=json.loads(p.read_text());d['version']='1.0.0-alpha.8.57'
    if isinstance(d.get('packages'),dict) and '' in d['packages']:d['packages']['']['version']='1.0.0-alpha.8.57'
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')

print('PASS: ENDLUME 8.57 strict master frame-lifetime hotfix applied')
