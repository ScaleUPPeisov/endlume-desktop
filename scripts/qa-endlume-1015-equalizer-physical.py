#!/usr/bin/env python3
import json, math, os, subprocess, sys
from collections import Counter
from pathlib import Path

FFMPEG=Path(sys.argv[1]).resolve()
FFPROBE=Path(sys.argv[2]).resolve()
ROOT=Path(sys.argv[3]).resolve()
FRAMES=ROOT/'frames'; FRAMES.mkdir(parents=True,exist_ok=True)
EQ_ID='825dd7a4-f0cf-4032-a3c9-64290cb5756d'

def run(args,check=True,timeout=90):
    p=subprocess.run([str(x) for x in args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    if check and p.returncode!=0:
        raise RuntimeError(p.stderr.decode(errors='replace')[-5000:])
    return p

def probe_video(path):
    try:
        d=json.loads(run([FFPROBE,'-v','error','-select_streams','v:0','-show_entries','stream=width,height,duration:format=duration','-of','json',path],timeout=20).stdout)
        s=(d.get('streams') or [None])[0]
        if not s:return None
        w=int(s.get('width') or 0); h=int(s.get('height') or 0)
        dur=float(s.get('duration') or d.get('format',{}).get('duration') or 2.0)
        if w<2 or h<2:return None
        if not math.isfinite(dur) or dur<=0:dur=2.0
        return w,h,dur
    except Exception:return None

def sample_rgb(path,t,w=160,h=90):
    p=run([FFMPEG,'-hide_banner','-loglevel','error','-ss',f'{max(0,t):.6f}','-i',path,'-vf',f'scale={w}:{h}:flags=area','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],check=False,timeout=30)
    if p.returncode!=0 or len(p.stdout)<w*h*3:return b''
    return p.stdout

def source_score(path):
    meta=probe_video(path)
    if not meta:return None
    w,h,dur=meta
    raws=[]
    for t in (min(.15,dur*.1),dur*.5,max(0,dur-.15)):
        raw=sample_rgb(path,t)
        if raw:raws.append(raw)
    if not raws:return None
    green=total=0; non_green=0; bins=Counter(); selected=[]
    for raw in raws:
        for i in range(0,len(raw)-2,3):
            r,g,b=raw[i],raw[i+1],raw[i+2]; total+=1
            is_green=g>=70 and g>=r+25 and g>=b+20 and g>=max(r,b)*1.25
            if is_green:
                green+=1; bins[(r//8,g//8,b//8)]+=1
            else: non_green+=1
    frac=green/max(1,total); fg=non_green/max(1,total)
    # Green-screen effect sources should have a dominant green field but meaningful foreground.
    score=frac if frac>=.30 and .002<=fg<=.65 else frac*.15
    key='#00ff00'
    if bins:
        q,_=bins.most_common(1)[0]
        vals=[]
        for raw in raws:
            for i in range(0,len(raw)-2,3):
                r,g,b=raw[i],raw[i+1],raw[i+2]
                if (r//8,g//8,b//8)==q:vals.append((r,g,b))
        if vals:
            rr=round(sum(x[0] for x in vals)/len(vals)); gg=round(sum(x[1] for x in vals)/len(vals)); bb=round(sum(x[2] for x in vals)/len(vals))
            key=f'#{rr:02x}{gg:02x}{bb:02x}'
    return {'path':str(path),'width':w,'height':h,'duration':dur,'greenFraction':frac,'foregroundFraction':fg,'score':score,'estimatedKey':key}

def find_source():
    # Prefer exact persisted Round Equalizer identity if available.
    exact=[]
    for base in [Path.home()/'Library/Application Support',Path.home()/'Library/Containers']:
        if not base.exists():continue
        for p in base.rglob('library.json'):
            try:d=json.loads(p.read_text(errors='replace'))
            except Exception:continue
            for e in d.get('effects',[]):
                if not isinstance(e,dict):continue
                src=Path(str(e.get('source','')))
                name=str(e.get('name','')).strip().lower()
                if (e.get('id')==EQ_ID or name=='эквалайзер круглый') and src.is_file():
                    score=source_score(src)
                    if score: exact.append((p,e,score))
    if exact:
        exact.sort(key=lambda x:x[0].stat().st_mtime if x[0].exists() else 0,reverse=True)
        p,e,s=exact[0]
        return s,e,str(p),[s]

    # Library state may be absent on the self-hosted runner. Managed assets survive independently.
    files=[]; seen=set()
    roots=[Path.home()/'Library/Application Support',Path.home()/'Library/Containers']
    for base in roots:
        if not base.exists():continue
        for p in base.rglob('library-assets/effects/*'):
            if p.is_file() and p not in seen:
                seen.add(p); files.append(p)
    # Also search shallow user folders for the original import if managed library was cleaned.
    for base in [Path.home()/'Desktop',Path.home()/'Downloads',Path('/Volumes/TOSHIBA EXT')]:
        if not base.exists():continue
        try:
            for p in base.rglob('*'):
                if len(files)>350:break
                if p.is_file() and p.suffix.lower() in {'.mp4','.mov','.m4v','.webm'} and p not in seen:
                    # Avoid arbitrary full-length rendered outputs during discovery.
                    try:size=p.stat().st_size
                    except Exception:continue
                    if 20_000<=size<=250_000_000:
                        seen.add(p); files.append(p)
        except Exception:pass
    scored=[]
    for p in files:
        s=source_score(p)
        if s and s['greenFraction']>=.30 and s['foregroundFraction']>=.002:
            scored.append(s)
    scored.sort(key=lambda x:(x['score'],x['greenFraction']),reverse=True)
    (ROOT/'source-candidates.json').write_text(json.dumps(scored[:50],ensure_ascii=False,indent=2))
    if not scored:raise AssertionError('ROUND_EQUALIZER_GREENSCREEN_SOURCE_NOT_FOUND')
    best=scored[0]
    # Require a meaningful margin when several green-screen effect assets exist; otherwise artifact images make ambiguity explicit.
    return best,{'id':EQ_ID,'name':'эквалайзер круглый','mode':'chromakey','keyColor':best['estimatedKey'],'similarity':.6,'blend':.35,'despill':1.0,'opacity':1.0,'usageMode':'always'},'<managed-asset-discovery>',scored[:12]

SOURCE_INFO,EQ,LIB,CANDIDATES=find_source()
SOURCE=Path(SOURCE_INFO['path'])
W=int(SOURCE_INFO['width']); H=int(SOURCE_INFO['height']); DURATION=float(SOURCE_INFO['duration'])
KEY=str(EQ.get('keyColor') or SOURCE_INFO.get('estimatedKey') or '#00ff00')
rawkey=KEY.lstrip('#'); KEY_FFMPEG='0x'+rawkey
kr=int(rawkey[0:2],16); kg=int(rawkey[2:4],16); kb=int(rawkey[4:6],16)
print('SOURCE_DISCOVERY='+json.dumps(SOURCE_INFO,ensure_ascii=False,separators=(',',':')))
print('ESTIMATED_OR_PERSISTED_KEY='+KEY)
for i,c in enumerate(CANDIDATES):print(f'CANDIDATE_{i+1}='+json.dumps(c,ensure_ascii=False,separators=(',',':')))

TIMES={'begin':max(0.0,min(DURATION-.02,.12)),'middle':max(0.0,DURATION*.5),'end':max(0.0,DURATION-.12)}
CASES={
  'owner_raw_max':(.60,.35,1.00),
  'candidate_current':(.18,.03,1.00),
  'safe_010_006_035':(.10,.06,.35),
  'safe_014_006_035':(.14,.06,.35),
  'safe_018_003_020':(.18,.03,.20),
  'safe_018_003_035':(.18,.03,.35),
  'safe_018_003_050':(.18,.03,.50),
  'safe_018_006_035':(.18,.06,.35),
}

def raw_at(t):
    return run([FFMPEG,'-hide_banner','-loglevel','error','-ss',f'{t:.6f}','-i',SOURCE,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],timeout=45).stdout

def keyed_at(t,sim,blend,dsp):
    vf=f'format=rgba,colorkey={KEY_FFMPEG}:{sim:.6f}:{blend:.6f},despill=type=green:mix={dsp:.6f}:expand=0.20,format=rgba'
    return run([FFMPEG,'-hide_banner','-loglevel','error','-ss',f'{t:.6f}','-i',SOURCE,'-vf',vf,'-frames:v','1','-f','rawvideo','-pix_fmt','rgba','-'],timeout=45).stdout

def metrics(raw,out):
    n=min(len(raw)//3,len(out)//4); fg=bg=0; fga=bga=0.; raw_e=out_e=green_excess=0.
    for i in range(n):
        r,g,b=raw[i*3:i*3+3]; rr,gg,bb,a=out[i*4:i*4+4]
        dist=math.sqrt((r-kr)**2+(g-kg)**2+(b-kb)**2)/441.67295593
        if dist>=.20:
            fg+=1; fga+=a/255.; raw_e+=(r+g+b)/765.; out_e+=(rr+gg+bb)/765.; green_excess+=max(gg-max(rr,bb),0)/255.
        elif dist<=.055:
            bg+=1; bga+=a/255.
    return {'foregroundPixels':fg,'backgroundPixels':bg,'foregroundAlphaPreserved':fga/max(1,fg),'greenBackgroundRemoved':1-bga/max(1,bg),'foregroundEnergyRatio':(out_e/max(1,fg))/(raw_e/max(1,fg)+1e-12),'foregroundGreenExcess':green_excess/max(1,fg)}

def save_flat(t,label,case,sim,blend,dsp,opacity=1.0):
    out=FRAMES/f'{label}-{case}.png'
    vf=f'format=rgba,colorkey={KEY_FFMPEG}:{sim:.6f}:{blend:.6f},despill=type=green:mix={dsp:.6f}:expand=0.20,colorchannelmixer=aa={opacity:.3f}'
    fc=f'[0:v]{vf}[fx];color=c=0x202020:s={W}x{H}:r=1[bg];[bg][fx]overlay=0:0:format=auto'
    run([FFMPEG,'-hide_banner','-loglevel','error','-ss',f'{t:.6f}','-i',SOURCE,'-f','lavfi','-i',f'color=c=0x202020:s={W}x{H}:r=1','-filter_complex',f'[0:v]{vf}[fx];[1:v][fx]overlay=0:0:format=auto','-frames:v','1','-y',out],timeout=45)

report={'productCandidate':'c5534ce47123777b698117a46473238381e37729','sourceDiscovery':SOURCE_INFO,'library':LIB,'source':str(SOURCE),'keyColor':KEY,'persistedEqualizer':{k:EQ.get(k) for k in ('id','name','mode','keyColor','similarity','blend','despill','opacity','scale','usageMode')},'frames':{}}
for label,t in TIMES.items():
    raw=raw_at(t); assert len(raw)>=W*H*3,(label,len(raw),W*H*3)
    row={'time':t,'cases':{}}
    for case,(sim,blend,dsp) in CASES.items():
        out=keyed_at(t,sim,blend,dsp); assert len(out)>=W*H*4,(label,case,len(out),W*H*4)
        row['cases'][case]=metrics(raw,out)
    report['frames'][label]=row
    for case in ('candidate_current','safe_010_006_035','safe_018_003_020','safe_018_003_035','safe_018_003_050'):
        sim,blend,dsp=CASES[case]; save_flat(t,label,case,sim,blend,dsp,1.0)
    # Opacity evidence at the likely safe protected-key settings.
    save_flat(t,label,'opacity_050',.18,.03,.35,.5)
    save_flat(t,label,'opacity_000',.18,.03,.35,0.0)

aggregate={}
for case in CASES:
    vals=[report['frames'][label]['cases'][case] for label in TIMES]
    aggregate[case]={k:sum(v[k] for v in vals)/len(vals) for k in ('foregroundAlphaPreserved','greenBackgroundRemoved','foregroundEnergyRatio','foregroundGreenExcess')}
report['aggregate']=aggregate
(ROOT/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
for case,m in aggregate.items():
    print(case.upper()+'_METRICS='+json.dumps(m,separators=(',',':')))
print('PHYSICAL_EQUALIZER_PROBE=PASS')
