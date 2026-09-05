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

# Fix 1: a cached keyed Effect must never end the Strict master timeline.
# Keep the base timeline alive and let -stream_loop -1 repeat the cached Effect.
old='graph.push_str(&format!(";[{idx}:v]fps={},format=argb[{fx}];[{base}][{fx}]overlay=x=\'{x}\':y=\'{y}\':shortest=1:eof_action=repeat:format=auto[{next}]",s.fps));base=next;continue'
new='graph.push_str(&format!(";[{idx}:v]fps={},setpts=PTS-STARTPTS,format=argb[{fx}];[{base}][{fx}]overlay=x=\'{x}\':y=\'{y}\':shortest=0:repeatlast=1:eof_action=repeat:format=auto[{next}]",s.fps));base=next;continue'
s=once(s,old,new,'strict-prealpha lifetime')

# Fix 2: physical Apple-Silicon diagnostics proved that a single HEVC
# VideoToolbox GOP spanning the full 3381-frame master is not safely decodable:
# it writes all 3381 packets but ffprobe can decode only 2048 frames.  GOP 1800
# and 1200 both decode 3381/3381; 1800 was the fastest valid result.  Preserve
# the full master frame count and quality, but cap only the keyframe interval.
old='let frames=(s.fps.max(1) as f64*duration.max(2.0)).round().max(1.0) as u32;\n  let g=frames.to_string();'
new='let frames=(s.fps.max(1) as f64*duration.max(2.0)).round().max(1.0) as u32;\n  let g=frames.min(1800).to_string();'
s=once(s,old,new,'VideoToolbox safe GOP cap')

# Do not silently accept a truncated master. The exact frame assertion stays.
s=s.replace('Strict 8.56 master: {got} кадров вместо {master_frames}','Strict 8.57 master: {got} кадров вместо {master_frames}')
s=s.replace('Strict 8.56: fidelity master полного Effects-цикла','Strict 8.57: fidelity master полного Effects-цикла')
s=s.replace('Strict 8.56 zero-copy готов','Strict 8.57 zero-copy готов')
R.write_text(s)

# Version only for manifests.
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

# Keep visible Update Center in sync with the installed bundle.
P=ROOT/'src/pages/SettingsPage.tsx'
ui=P.read_text()
ui=once(ui,'ENDLUME Studio 1.0.0-alpha.8.41','ENDLUME Studio 1.0.0-alpha.8.57','settings visible version')
ui=once(ui,"update.current||'1.0.0-alpha.8.41'","update.current||'1.0.0-alpha.8.57'",'settings updater fallback')
ui=once(ui,'Версия <b>1.0.0-alpha.8.41</b>','Версия <b>1.0.0-alpha.8.57</b>','about visible version')
ui=once(ui,'Обновлено <b>31.08.2026</b>','Обновлено <b>05.09.2026</b>','about visible date')
P.write_text(ui)

H=ROOT/'src/components/ReleaseHistory.tsx'
h=H.read_text()
anchor="const releases:Release[]=[\n  {version:'1.0.0-alpha.8.41',date:'31.08.2026',current:true,title:'60 FPS • Stability • Gapless Audio • Chroma',items:["
insert="""const releases:Release[]=[
  {version:'1.0.0-alpha.8.57',date:'05.09.2026',current:true,title:'Strict Master Frame Hotfix • Safe VideoToolbox GOP',items:[
    'Исправлено преждевременное завершение keyed Effects: overlay больше не обрывает Strict master по длине первого короткого эффекта.',
    'HEVC VideoToolbox GOP ограничен безопасными 1800 кадрами: полный master остаётся 3381 кадров, но больше не использует проблемный GOP на весь цикл.',
    'Strict master обязан сформировать и декодировать 3381 кадров при 1920×1080/60 FPS; усечённый master не принимается.',
    'Экран Обновления и О программе синхронизирован с текущей версией 8.57.',
    'VYRON bridge, whole-track audio, zero-copy, Subscribe, updater identity и подпись релиза сохранены.'
  ]},
  {version:'1.0.0-alpha.8.56',date:'05.09.2026',current:false,title:'Render Isolation • Strict Output Contract',items:[
    'Strict one-image render изолирован от software fallback и случайных legacy-путей.',
    'Whole-track audio и нулевой crossfade закреплены для производственного VYRON-пайплайна.',
    'Финальный файл проходит строгий контракт размера 400–700 МБ и проверку результата до публикации.'
  ]},
  {version:'1.0.0-alpha.8.41',date:'31.08.2026',current:false,title:'60 FPS • Stability • Gapless Audio • Chroma',items:["""
h=once(h,anchor,insert,'release history current version')
H.write_text(h)

print('PASS: ENDLUME 8.57 strict master lifetime + safe VideoToolbox GOP + visible-version hotfix applied')
