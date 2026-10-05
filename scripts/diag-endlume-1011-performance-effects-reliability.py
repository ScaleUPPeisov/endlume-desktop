#!/usr/bin/env python3
import json, os, re, subprocess, sys, tempfile, time
from pathlib import Path

APP=Path(sys.argv[1]).resolve()
FFMPEG=Path(sys.argv[2]).resolve()
FFPROBE=Path(sys.argv[3]).resolve()
REPORT=Path(sys.argv[4]).resolve()
VOL=Path('/Volumes/TOSHIBA EXT')
OUT=VOL/'ВАЙРОН'/'Render'/'Brewroom Jazz'
IMAGE={'.jpg','.jpeg','.png','.webp','.bmp','.tif','.tiff','.heic','.avif'}
AUDIO={'.mp3','.wav','.m4a','.aac','.flac','.ogg','.opus','.aiff','.aif','.alac'}

assert APP.is_file(), APP
assert FFMPEG.is_file() and FFPROBE.is_file(), (FFMPEG,FFPROBE)
assert VOL.is_dir(), f'TOSHIBA_NOT_MOUNTED:{VOL}'
assert OUT.is_dir(), f'TOSHIBA_RENDER_DIR_MISSING:{OUT}'
REPORT.parent.mkdir(parents=True,exist_ok=True)

def run(args,check=True,timeout=300,env=None):
    return subprocess.run([str(x) for x in args],check=check,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,env=env)

def probe(path):
    return json.loads(run([FFPROBE,'-v','error','-show_entries','stream=codec_type,codec_name,width,height,avg_frame_rate,pix_fmt,sample_rate,channels,bit_rate:format=duration,size,bit_rate','-of','json',path],timeout=90).stdout)

def duration(path):
    try:
        p=probe(path)
        return float(p.get('format',{}).get('duration') or 0.0)
    except Exception:
        return None

def resolve_project():
    roots=[]
    data_root=Path.home()/'Library/Application Support/studio.endlume.desktop'
    for state_name in ('queue.json','recovery.json'):
        p=data_root/state_name
        if not p.is_file(): continue
        try: d=json.loads(p.read_text())
        except Exception: continue
        jobs=[]
        if isinstance(d,dict):
            if isinstance(d.get('active'),dict): jobs.append(d['active'])
            jobs.extend(x for x in (d.get('pending') or []) if isinstance(x,dict))
        for job in jobs:
            proj=job.get('project') or {}
            q=Path(str(proj.get('path','')))
            if q.is_dir(): roots.append(q)
    if not roots:
        base=VOL/'ВАЙРОН'
        for p in base.rglob('*'):
            if not p.is_dir(): continue
            try: files=[x for x in p.iterdir() if x.is_file() and not x.name.startswith('.')]
            except Exception: continue
            if any(x.suffix.lower() in IMAGE for x in files) and sum(x.suffix.lower() in AUDIO for x in files)>=10:
                roots.append(p); break
    candidates=[]
    for base in roots:
        for d in [base]+[p for p in base.rglob('*') if p.is_dir()]:
            try: files=[p for p in d.iterdir() if p.is_file() and not p.name.startswith('.') and not p.name.startswith('._')]
            except Exception: continue
            media=sorted([p for p in files if p.suffix.lower() in IMAGE],key=lambda x:x.name.lower())
            songs=sorted([p for p in files if p.suffix.lower() in AUDIO],key=lambda x:x.name.lower())
            if media and len(songs)>=10: candidates.append((len(songs),-len(str(d)),d,media,songs))
    assert candidates,'REAL_1_IMAGE_10_TRACK_PROJECT_NOT_FOUND'
    _,_,project,media,songs=max(candidates)
    return project,media,songs

def load_library():
    candidates=[]
    for base in [Path.home()/'Library/Application Support',Path.home()/'Library/Containers']:
        if not base.exists(): continue
        for p in base.rglob('library.json'):
            try:
                if p.stat().st_size>10_000_000: continue
                d=json.loads(p.read_text())
                if isinstance(d,dict) and isinstance(d.get('effects'),list): candidates.append((p,d))
            except Exception: continue
    assert candidates,'ENDLUME_LIBRARY_JSON_NOT_FOUND'
    candidates.sort(key=lambda x:(len(x[1].get('effects',[])),x[0].stat().st_mtime),reverse=True)
    return candidates[0]

project,media,songs=resolve_project()
lib_path,lib=load_library()
raw_effects=[dict(x) for x in lib.get('effects',[]) if isinstance(x,dict)]
real_effects=[]
inventory=[]
for index,e in enumerate(raw_effects):
    src=Path(str(e.get('source','')))
    exists=src.is_file()
    row={
        'index':index,
        'id':str(e.get('id','')),
        'name':str(e.get('name','')),
        'source':str(src),
        'exists':exists,
        'enabled':bool(e.get('enabled',False)),
        'usageMode':e.get('usageMode'),
        'mode':e.get('mode'),
        'sizeBytes':src.stat().st_size if exists else None,
        'durationSec':duration(src) if exists else None,
    }
    inventory.append(row)
    if exists and str(e.get('id','')).strip(): real_effects.append(e)

print('SOURCE_PROJECT='+str(project))
print('SOURCE_IMAGE='+str(media[0]))
print('SOURCE_TRACKS_AVAILABLE='+str(len(songs)))
print('LIBRARY_PATH='+str(lib_path))
print('REAL_EFFECT_COUNT='+str(len(real_effects)))
for row in inventory:
    print('EFFECT_INVENTORY='+json.dumps(row,ensure_ascii=False,sort_keys=True))

subs=[]
for s in lib.get('subscribes',[]) if isinstance(lib.get('subscribes'),list) else []:
    if isinstance(s,dict) and Path(str(s.get('source',''))).is_file():
        x=dict(s); x['enabled']=True; x['usageMode']='interval'; x['intervalSec']=240.0; x['repeatEverySec']=240.0; x['firstAppearance']='after-interval'; x['showDurationSec']=8.0; subs.append(x)
        break

settings={'width':1920,'height':1080,'fps':60,'codec':'h265','bitrateMbps':8.0,'durationHours':2.0,'durationMode':'whole-track','loopMode':'image','crossfadeSec':0.0,'normalizeLufs':False,'outputDir':str(OUT),'preset':'fast','encoderPreference':'auto'}
base_project={'path':str(project),'media':[str(media[0])],'audio':[str(x) for x in songs[:10]],'valid':True,'error':None,'anchors':{}}
tmp=Path(tempfile.mkdtemp(prefix='endlume1011-perf-effects-diag-'))
results=[]

def normalize_effect(e):
    x=dict(e); x['enabled']=True
    if x.get('usageMode') in (None,'off'): x['usageMode']='always'
    return x

def render_case(label,effects):
    fixture=tmp/f'{label}-job.json'; result=tmp/f'{label}-result.json'
    job={'project':dict(base_project,id=f'diag-{label}',name=f'ENDLUME 10.0.11 DIAG {label}'),'settings':settings,'effects':[normalize_effect(e) for e in effects],'subscribes':subs,'ambient':None}
    fixture.write_text(json.dumps({'jobs':[job]},ensure_ascii=False,indent=2))
    env=os.environ.copy(); env.update({'ENDLUME_E2E_RENDER_JOB':str(fixture),'ENDLUME_E2E_RESULT':str(result),'RUST_BACKTRACE':'1'})
    started=time.perf_counter(); p=run([APP],check=False,timeout=360,env=env); wall=time.perf_counter()-started
    (tmp/f'{label}.stdout').write_text(p.stdout); (tmp/f'{label}.stderr').write_text(p.stderr)
    diag=[]
    for line in p.stderr.splitlines():
        if 'ENDLUME_DIAG ' not in line: continue
        try: diag.append(json.loads(line.split('ENDLUME_DIAG ',1)[1].strip()))
        except Exception: pass
    if p.returncode!=0 or not result.is_file():
        row={'label':label,'ok':False,'processExit':p.returncode,'wallSeconds':wall,'error':p.stderr[-5000:],'diag':diag[-80:]}
        results.append(row); print('RENDER_CASE='+json.dumps(row,ensure_ascii=False)); return
    raw=json.loads(result.read_text()); rr=(raw.get('results') or [{}])[0]
    out_path=Path(str(rr.get('outputPath','')))
    meta=probe(out_path) if out_path.is_file() else {}
    video=next((x for x in meta.get('streams',[]) if x.get('codec_type')=='video'),{})
    audio=next((x for x in meta.get('streams',[]) if x.get('codec_type')=='audio'),{})
    row={'label':label,'ok':raw.get('status')=='passed' and out_path.is_file(),'wallSeconds':float(rr.get('wallSeconds') or wall),'processWallSeconds':wall,'outputBytes':out_path.stat().st_size if out_path.is_file() else None,'durationSec':float(meta.get('format',{}).get('duration') or 0.0) if meta else None,'videoCodec':video.get('codec_name'),'width':video.get('width'),'height':video.get('height'),'fps':video.get('avg_frame_rate'),'pixelFormat':video.get('pix_fmt'),'audioCodec':audio.get('codec_name'),'audioSampleRate':audio.get('sample_rate'),'audioChannels':audio.get('channels'),'encoder':rr.get('encoder'),'fastPath':rr.get('fastPath'),'effects':[{'id':e.get('id'),'name':e.get('name'),'source':e.get('source')} for e in effects],'diag':diag[-120:]}
    results.append(row); print('RENDER_CASE='+json.dumps(row,ensure_ascii=False,sort_keys=True))
    if out_path.is_file():
        try: out_path.unlink()
        except Exception: pass

render_case('NO_EFFECT',[])
for i,e in enumerate(real_effects): render_case(f'EFFECT_{i+1}',[e])
active=[e for e in real_effects if e.get('enabled')]
if len(active)>1: render_case('ALL_ENABLED',active)

report={'sourceSha':'2e4e958d08927eaf098dc348fdfaed34ecb92b56','project':str(project),'libraryPath':str(lib_path),'effectInventory':inventory,'realEffectCount':len(real_effects),'subscribePresent':bool(subs),'results':results,'threeEffectGate':len(real_effects)==3}
REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('REPORT_PATH='+str(REPORT))
print('THREE_EFFECT_GATE='+('PASS' if len(real_effects)==3 else 'BLOCKED'))
print('DIAGNOSTIC_COMPLETE=YES')
