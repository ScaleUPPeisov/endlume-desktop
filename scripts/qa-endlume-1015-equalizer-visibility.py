#!/usr/bin/env python3
import json, math, subprocess, sys
from pathlib import Path

FFMPEG=Path(sys.argv[1]).resolve()
FFPROBE=Path(sys.argv[2]).resolve()
ROOT=Path(sys.argv[3]).resolve()
FRAMES=ROOT/'frames'
FRAMES.mkdir(parents=True,exist_ok=True)
EQ_ID='825dd7a4-f0cf-4032-a3c9-64290cb5756d'

def run(args,check=True,timeout=120):
    p=subprocess.run([str(x) for x in args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    if check and p.returncode!=0:
        raise RuntimeError(p.stderr.decode(errors='replace')[-6000:])
    return p

def load_equalizer():
    found=[]
    for base in [Path.home()/'Library/Application Support',Path.home()/'Library/Containers']:
        if not base.exists(): continue
        for p in base.rglob('library.json'):
            try:
                if p.stat().st_size>10_000_000: continue
                data=json.loads(p.read_text(errors='replace'))
            except Exception:
                continue
            for effect in data.get('effects',[]):
                if not isinstance(effect,dict): continue
                src=Path(str(effect.get('source','')))
                name=str(effect.get('name','')).strip().lower()
                if (effect.get('id')==EQ_ID or name=='эквалайзер круглый') and src.is_file():
                    found.append((p,effect,src))
    if not found: raise AssertionError('ROUND_EQUALIZER_PHYSICAL_SOURCE_NOT_FOUND')
    found.sort(key=lambda item:item[0].stat().st_mtime,reverse=True)
    return found[0]

LIB,EQ,SOURCE=load_equalizer()
meta=json.loads(run([FFPROBE,'-v','error','-show_entries','stream=width,height,duration:format=duration','-select_streams','v:0','-of','json',SOURCE]).stdout)
stream=meta['streams'][0]
W=int(stream['width']); H=int(stream['height'])
DURATION=float(stream.get('duration') or meta.get('format',{}).get('duration') or 2.0)
if not math.isfinite(DURATION) or DURATION<=0: DURATION=2.0
TIMES={'begin':max(0.0,min(DURATION-0.02,0.12)),'middle':max(0.0,DURATION/2.0),'end':max(0.0,DURATION-0.12)}

# Candidate currently hard-overrides Round Equalizer to 0.18/0.03 but leaves despill at owner value 1.0.
CASES={
    'owner_raw_max':(0.60,0.35,1.00),
    'candidate_current':(0.18,0.03,1.00),
    'safe_010_006_035':(0.10,0.06,0.35),
    'safe_014_006_035':(0.14,0.06,0.35),
    'safe_018_003_020':(0.18,0.03,0.20),
    'safe_018_003_035':(0.18,0.03,0.35),
    'safe_018_003_050':(0.18,0.03,0.50),
    'safe_018_006_035':(0.18,0.06,0.35),
}

def raw_at(t):
    return run([FFMPEG,'-hide_banner','-loglevel','error','-ss',f'{t:.6f}','-i',SOURCE,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],timeout=60).stdout

def keyed_at(t,sim,blend,despill):
    vf=f'format=rgba,colorkey=0x00ff00:{sim:.6f}:{blend:.6f},despill=type=green:mix={despill:.6f}:expand=0.20,format=rgba'
    return run([FFMPEG,'-hide_banner','-loglevel','error','-ss',f'{t:.6f}','-i',SOURCE,'-vf',vf,'-frames:v','1','-f','rawvideo','-pix_fmt','rgba','-'],timeout=60).stdout

def stats(raw,out):
    n=min(len(raw)//3,len(out)//4)
    fg_n=bg_n=0
    fg_alpha=bg_alpha=0.0
    raw_energy=out_energy=0.0
    for i in range(n):
        r,g,b=raw[i*3:i*3+3]
        rr,gg,bb,a=out[i*4:i*4+4]
        dist=math.sqrt(r*r+(g-255)*(g-255)+b*b)/441.67295593
        if dist>=0.22:
            fg_n+=1; fg_alpha+=a/255.0
            raw_energy+=(r+g+b)/765.0
            out_energy+=(rr+gg+bb)/765.0
        elif dist<=0.055:
            bg_n+=1; bg_alpha+=a/255.0
    return {
        'foregroundAlphaPreserved':fg_alpha/max(1,fg_n),
        'greenBackgroundRemoved':1.0-bg_alpha/max(1,bg_n),
        'foregroundEnergyRatio':(out_energy/max(1,fg_n))/(raw_energy/max(1,fg_n)+1e-12),
        'foregroundPixels':fg_n,'backgroundPixels':bg_n,
    }

def save_flat(t,label,case,sim,blend,despill,opacity=1.0):
    keyed=FRAMES/f'{label}-{case}-keyed.png'
    vf=f'format=rgba,colorkey=0x00ff00:{sim:.6f}:{blend:.6f},despill=type=green:mix={despill:.6f}:expand=0.20,colorchannelmixer=aa={opacity:.6f},format=rgba'
    run([FFMPEG,'-hide_banner','-loglevel','error','-ss',f'{t:.6f}','-i',SOURCE,'-vf',vf,'-frames:v','1','-y',keyed],timeout=60)
    flat=FRAMES/f'{label}-{case}-flat.png'
    run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i',f'color=c=0x202020:s={W}x{H}:r=1','-i',keyed,'-filter_complex','[0:v][1:v]overlay=0:0:format=auto','-frames:v','1','-y',flat],timeout=60)
    return flat

report={
    'productCandidate':'c5534ce47123777b698117a46473238381e37729',
    'library':str(LIB),'source':str(SOURCE),'width':W,'height':H,'duration':DURATION,
    'persistedEqualizer':{k:EQ.get(k) for k in ('id','name','mode','keyColor','similarity','blend','despill','opacity','scale','usageMode')},
    'forcedOwnerTest':{'similarity':0.60,'blend':0.35,'despill':1.0,'opacity':1.0},
    'candidateEffectiveAtOwnerTest':{'similarity':0.18,'blend':0.03,'despill':1.0,'opacity':1.0},
    'frames':{}
}
for label,t in TIMES.items():
    raw=raw_at(t)
    assert len(raw)>=W*H*3,(label,len(raw),W*H*3)
    item={'time':t,'cases':{}}
    for case,(sim,blend,dsp) in CASES.items():
        out=keyed_at(t,sim,blend,dsp)
        assert len(out)>=W*H*4,(label,case,len(out),W*H*4)
        item['cases'][case]=stats(raw,out)
    report['frames'][label]=item
    save_flat(t,label,'current',0.18,0.03,1.0,1.0)
    save_flat(t,label,'safe',0.18,0.03,0.35,1.0)

aggregate={}
for case in CASES:
    vals=[report['frames'][label]['cases'][case] for label in TIMES]
    aggregate[case]={key:sum(v[key] for v in vals)/len(vals) for key in ('foregroundAlphaPreserved','greenBackgroundRemoved','foregroundEnergyRatio')}
report['aggregate']=aggregate
eligible=[(case,m) for case,m in aggregate.items() if case.startswith('safe_') and m['greenBackgroundRemoved']>=0.985 and m['foregroundAlphaPreserved']>=0.88]
assert eligible,aggregate
selected=max(eligible,key=lambda x:(x[1]['foregroundEnergyRatio'],x[1]['foregroundAlphaPreserved'],x[1]['greenBackgroundRemoved']))
report['selectedSafeCase']=selected[0]
(ROOT/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))

cur=aggregate['candidate_current']; rawmax=aggregate['owner_raw_max']; safe=selected[1]
print('PHYSICAL_LIBRARY='+str(LIB))
print('ROUND_EQUALIZER_SOURCE='+str(SOURCE))
print('PERSISTED_EQUALIZER='+json.dumps(report['persistedEqualizer'],ensure_ascii=False,separators=(',',':')))
print('OWNER_RAW_MAX_BG_REMOVAL=%.6f'%rawmax['greenBackgroundRemoved'])
print('OWNER_RAW_MAX_FG_ALPHA=%.6f'%rawmax['foregroundAlphaPreserved'])
print('OWNER_RAW_MAX_FG_ENERGY=%.6f'%rawmax['foregroundEnergyRatio'])
print('CANDIDATE_CURRENT_BG_REMOVAL=%.6f'%cur['greenBackgroundRemoved'])
print('CANDIDATE_CURRENT_FG_ALPHA=%.6f'%cur['foregroundAlphaPreserved'])
print('CANDIDATE_CURRENT_FG_ENERGY=%.6f'%cur['foregroundEnergyRatio'])
print('SELECTED_SAFE_CASE='+selected[0])
print('SAFE_BG_REMOVAL=%.6f'%safe['greenBackgroundRemoved'])
print('SAFE_FG_ALPHA=%.6f'%safe['foregroundAlphaPreserved'])
print('SAFE_FG_ENERGY=%.6f'%safe['foregroundEnergyRatio'])
print('CURRENT_TO_SAFE_ENERGY_GAIN=%.6f'%(safe['foregroundEnergyRatio']/max(cur['foregroundEnergyRatio'],1e-12)))
print('PHYSICAL_EQUALIZER_PROBE=PASS')
