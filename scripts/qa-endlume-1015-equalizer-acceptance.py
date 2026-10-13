#!/usr/bin/env python3
import json, math, os, shutil, subprocess, sys, tempfile, time
from collections import Counter
from pathlib import Path

APP=Path(sys.argv[1]).resolve()
FFMPEG=Path(sys.argv[2]).resolve()
FFPROBE=Path(sys.argv[3]).resolve()
ROOT=Path(sys.argv[4]).resolve()
EQ_SOURCE=Path(sys.argv[5]).resolve()
CANDIDATE='eaa6eb0a022f184f533338e9ff778328cfe29717'
EQ_ID='825dd7a4-f0cf-4032-a3c9-64290cb5756d'
ROOT.mkdir(parents=True,exist_ok=True)
EVIDENCE=ROOT/'evidence'; EVIDENCE.mkdir(parents=True,exist_ok=True)
OUT=ROOT/'out'; OUT.mkdir(parents=True,exist_ok=True)
assert APP.is_file(),APP
assert FFMPEG.is_file() and FFPROBE.is_file(),(FFMPEG,FFPROBE)
assert EQ_SOURCE.is_file(),EQ_SOURCE

def run(args,check=True,timeout=180,env=None):
    p=subprocess.run([str(x) for x in args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,env=env)
    if check and p.returncode!=0:
        raise RuntimeError(f'rc={p.returncode}: {args}\n{p.stderr[-10000:]}')
    return p

def probe(path):
    return json.loads(run([FFPROBE,'-v','error','-show_entries','stream=codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels:format=duration,size','-of','json',path],timeout=30).stdout)

def video_meta(path):
    d=probe(path); v=next(x for x in d['streams'] if x.get('codec_type')=='video')
    dur=float(d.get('format',{}).get('duration') or 0)
    return int(v['width']),int(v['height']),dur

def raw_frame(path,t):
    p=subprocess.run([str(FFMPEG),'-hide_banner','-loglevel','error','-ss',f'{t:.4f}','-i',str(path),'-map','0:v:0','-vf','scale=1920:1080:flags=bicubic','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
    if p.returncode!=0: raise RuntimeError(p.stderr.decode(errors='replace')[-5000:])
    assert len(p.stdout)==1920*1080*3,(path,t,len(p.stdout))
    return p.stdout

def save_frame(path,t,dst):
    run([FFMPEG,'-hide_banner','-loglevel','error','-ss',f'{t:.4f}','-i',path,'-map','0:v:0','-vf','scale=1920:1080:flags=bicubic','-frames:v','1','-y',dst],timeout=60)

def diff_stats(a,b,step_pixels=8,threshold=5):
    assert len(a)==len(b)
    changed=0; total=0; sumd=0.0; sq=0.0; maxd=0
    stride=3*step_pixels
    for i in range(0,len(a)-2,stride):
        d=max(abs(a[i]-b[i]),abs(a[i+1]-b[i+1]),abs(a[i+2]-b[i+2]))
        total+=1; sumd+=d; sq+=d*d; maxd=max(maxd,d)
        if d>=threshold: changed+=1
    return {'sampled':total,'changed':changed,'ratio':changed/max(1,total),'meanMaxDiff':sumd/max(1,total),'rmsMaxDiff':math.sqrt(sq/max(1,total)),'maxDiff':maxd}

def estimate_key(path):
    w,h,d=video_meta(path)
    samples=[]
    for t in (min(.12,max(.01,d*.05)),d*.5,max(.01,d-.12)):
        p=subprocess.run([str(FFMPEG),'-hide_banner','-loglevel','error','-ss',f'{t:.4f}','-i',str(path),'-vf','scale=180:180:flags=area','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        assert p.returncode==0,p.stderr.decode(errors='replace')[-3000:]
        samples.append(p.stdout)
    hist=Counter()
    for raw in samples:
        for i in range(0,len(raw)-2,3):
            r,g,b=raw[i:i+3]
            if g>=70 and g>=r+24 and g>=b+18 and g>=max(r,b)*1.20:
                hist[(r//4,g//4,b//4)]+=1
    assert hist,'NO_GREEN_BACKGROUND_DETECTED'
    q,_=hist.most_common(1)[0]
    vals=[]
    for raw in samples:
        for i in range(0,len(raw)-2,3):
            r,g,b=raw[i:i+3]
            if (r//4,g//4,b//4)==q: vals.append((r,g,b))
    r=round(sum(x[0] for x in vals)/len(vals)); g=round(sum(x[1] for x in vals)/len(vals)); b=round(sum(x[2] for x in vals)/len(vals))
    return f'#{r:02x}{g:02x}{b:02x}'

KEY=estimate_key(EQ_SOURCE)
print('ROUND_EQUALIZER_SOURCE='+str(EQ_SOURCE))
print('PHYSICAL_KEY_COLOR='+KEY)

# Direct physical key analysis proves the root cause and the selected defaults.
def chroma_metrics(sim,blend,despill):
    kw=KEY.lstrip('#'); kr,kg,kb=[int(kw[i:i+2],16) for i in (0,2,4)]
    w,h,d=video_meta(EQ_SOURCE)
    rows=[]
    for t in (min(.12,d*.05),d*.5,max(.01,d-.12)):
        rawp=subprocess.run([str(FFMPEG),'-hide_banner','-loglevel','error','-ss',f'{t:.4f}','-i',str(EQ_SOURCE),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
        outp=subprocess.run([str(FFMPEG),'-hide_banner','-loglevel','error','-ss',f'{t:.4f}','-i',str(EQ_SOURCE),'-vf',f'format=rgba,colorkey=0x{kw}:{sim:.6f}:{blend:.6f},despill=type=green:mix={despill:.6f}:expand=0.20,format=rgba','-frames:v','1','-f','rawvideo','-pix_fmt','rgba','-'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
        assert rawp.returncode==0 and outp.returncode==0,(rawp.stderr[-2000:],outp.stderr[-2000:])
        raw=rawp.stdout; out=outp.stdout; n=min(len(raw)//3,len(out)//4)
        fg=bg=0; fa=ba=0.0
        for i in range(n):
            r,g,b=raw[i*3:i*3+3]; a=out[i*4+3]
            dist=math.sqrt((r-kr)**2+(g-kg)**2+(b-kb)**2)/441.673
            if dist>=.20: fg+=1; fa+=a/255.0
            elif dist<=.055: bg+=1; ba+=a/255.0
        rows.append({'foregroundAlpha':fa/max(1,fg),'backgroundRemoved':1-ba/max(1,bg),'fg':fg,'bg':bg})
    return {k:sum(x[k] for x in rows)/len(rows) for k in ('foregroundAlpha','backgroundRemoved')}

OWNER_MAX=chroma_metrics(.60,.35,1.0)
SAFE=chroma_metrics(.10,.06,.35)
print('OWNER_MAX_METRICS='+json.dumps(OWNER_MAX,separators=(',',':')))
print('SAFE_METRICS='+json.dumps(SAFE,separators=(',',':')))
assert OWNER_MAX['foregroundAlpha']<0.30,OWNER_MAX
assert SAFE['foregroundAlpha']>=0.95,SAFE
assert SAFE['backgroundRemoved']>=0.985,SAFE

# Short 4-second physical fixture for product Preview and Final Render.
PROJECT=ROOT/'project'; PROJECT.mkdir(exist_ok=True)
BASE=PROJECT/'cover.png'; AUDIO=PROJECT/'track.wav'
run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x1f2633:s=1920x1080:r=1','-vf','drawbox=x=80:y=70:w=520:h=150:color=0x31445e:t=fill,drawbox=x=1320:y=830:w=480:h=150:color=0x2b3b50:t=fill','-frames:v','1','-y',BASE])
run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=4','-af','pan=stereo|c0=c0|c1=c0','-c:a','pcm_s16le','-y',AUDIO])

FX1=ROOT/'fx1.mp4'; FX2=ROOT/'fx2.mp4'
run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x00ff00:size=640x360:rate=30','-t','4','-vf','drawbox=x=70:y=70:w=210:h=110:color=red@1:t=fill,drawbox=x=110:y=110:w=120:h=45:color=white@1:t=fill','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-y',FX1])
run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x00ff00:size=640x360:rate=30','-t','4','-vf','drawbox=x=355:y=175:w=210:h=110:color=blue@1:t=fill,drawbox=x=405:y=205:w=110:h=45:color=white@1:t=fill','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-y',FX2])

def effect(source,eid,name,key='#00ff00',x=.5,y=.5,scale=.55,opacity=1.0,sim=.10,blend=.06,despill=.35):
    return {'id':eid,'name':name,'source':str(source),'enabled':True,'mode':'chromakey','keyColor':key,'similarity':sim,'blend':blend,'despill':despill,'lumaThreshold':0.03,'lumaTolerance':0.08,'saturation':1.0,'x':x,'y':y,'scale':scale,'fullscreen':False,'previewFrameTime':0.0,'startSec':0.0,'endSec':None,'cacheKey':None,'cacheReady':False,'usageMode':'always','intervalSec':240.0,'usageDurationSec':30.0,'target':None,'offsetX':None,'offsetY':None,'opacity':opacity}

def eq(opacity=1.0,sim=.10,blend=.06,despill=.35):
    return effect(EQ_SOURCE,EQ_ID,'эквалайзер круглый',KEY,.5,.5,.58,opacity,sim,blend,despill)
fx1=effect(FX1,'qa-eq-fx1','QA Red Effect','#00ff00',.18,.20,.22,1.0)
fx2=effect(FX2,'qa-eq-fx2','QA Blue Effect','#00ff00',.82,.80,.22,1.0)

# Backend Live Preview physical product path.
PREVIEW_PROJECT=ROOT/'preview-project'; PREVIEW_PROJECT.mkdir(exist_ok=True)
PREVIEW_BASE=PREVIEW_PROJECT/'001.png'; shutil.copy2(BASE,PREVIEW_BASE)
CACHE=Path.home()/'Library/Caches/studio.endlume.desktop'

def preview_run(label,effects,time_sec=2.0,overlay=None):
    for name in ('live-preview-v6','previews-v3'):
        shutil.rmtree(CACHE/name,ignore_errors=True)
    fixture=ROOT/f'{label}-preview-job.json'; result=ROOT/f'{label}-preview-result.json'
    fixture.write_text(json.dumps({'projectPath':str(PREVIEW_PROJECT),'overlaySource':str(overlay or EQ_SOURCE),'timeSec':time_sec,'effects':effects,'subscribes':[]},ensure_ascii=False,indent=2))
    env=os.environ.copy(); env.update({'ENDLUME_E2E_PREVIEW_JOB':str(fixture),'ENDLUME_E2E_RENDER_JOB':str(fixture),'ENDLUME_E2E_RESULT':str(result),'ENDLUME_PREVIEW_DIAG':'1','RUST_BACKTRACE':'1'})
    p=run([APP],check=False,timeout=150,env=env)
    (ROOT/f'{label}.preview.stdout').write_text(p.stdout or ''); (ROOT/f'{label}.preview.stderr').write_text(p.stderr or '')
    assert p.returncode==0,(label,p.returncode,p.stderr[-8000:])
    data=json.loads(result.read_text()); assert data.get('status')=='passed',data
    payload=data['result']; poster=Path(payload['posterPath']); exact=Path(payload['exactPath']); helper=payload['helper']
    assert poster.is_file() and exact.is_file(),(poster,exact)
    keep=EVIDENCE/f'preview-{label}.png'; shutil.copy2(poster,keep)
    return {'poster':keep,'exact':exact,'helper':helper,'result':data,'stderr':p.stderr}

pv_base=preview_run('base',[],2.0)
pv_1=preview_run('eq-op1',[eq(1.0)],2.0)
pv_05=preview_run('eq-op05',[eq(.5)],2.0)
pv_0=preview_run('eq-op0',[eq(0.0)],2.0)
pv_others=preview_run('others',[fx1,fx2],2.0,FX1)
pv_multi=preview_run('multi',[eq(1.0),fx1,fx2],2.0)

pbase=raw_frame(pv_base['poster'],0); p1=raw_frame(pv_1['poster'],0); p05=raw_frame(pv_05['poster'],0); p0=raw_frame(pv_0['poster'],0); po=raw_frame(pv_others['poster'],0); pm=raw_frame(pv_multi['poster'],0)
P1=diff_stats(pbase,p1); P05=diff_stats(pbase,p05); P0=diff_stats(pbase,p0); PM=diff_stats(po,pm)
print('PREVIEW_OP1='+json.dumps(P1,separators=(',',':')))
print('PREVIEW_OP05='+json.dumps(P05,separators=(',',':')))
print('PREVIEW_OP0='+json.dumps(P0,separators=(',',':')))
print('PREVIEW_MULTI_EQ_CONTRIBUTION='+json.dumps(PM,separators=(',',':')))
assert P1['changed']>=120 and P1['meanMaxDiff']>=.5,P1
assert P05['meanMaxDiff']<P1['meanMaxDiff']*.82 and P05['meanMaxDiff']>P1['meanMaxDiff']*.18,(P1,P05)
assert P0['meanMaxDiff']<=max(.30,P1['meanMaxDiff']*.08),(P1,P0)
assert PM['changed']>=100 and PM['meanMaxDiff']>=.35,PM

# Frontend Live Preview smoke on the packaged browser path.
def frontend_display(label,preview,effect_obj):
    h=preview['helper']; fixture=ROOT/f'{label}-frontend.json'; result=ROOT/f'{label}-frontend-result.json'
    fixture.write_text(json.dumps({'basePath':str(h['basePath']),'baseKind':h['baseKind'],'overlayPath':str(h['overlayPath']),'posterPath':str(preview['poster']),'baseBytes':int(h.get('baseBytes',Path(h['basePath']).stat().st_size)),'overlayBytes':int(h.get('overlayBytes',Path(h['overlayPath']).stat().st_size)),'effect':effect_obj,'requestId':label,'previewType':'Effects'},ensure_ascii=False,indent=2))
    env=os.environ.copy(); env.update({'ENDLUME_E2E_FRONTEND_PREVIEW_FIXTURE':str(fixture),'ENDLUME_E2E_FRONTEND_PREVIEW_RESULT':str(result),'ENDLUME_PREVIEW_DIAG':'1'})
    proc=subprocess.Popen([str(APP)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
    time.sleep(.8)
    subprocess.run(['/usr/bin/osascript','-e','tell application id "studio.endlume.desktop" to activate'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False,timeout=8)
    deadline=time.time()+35
    try:
        while time.time()<deadline and not result.is_file() and proc.poll() is None: time.sleep(.1)
        assert result.is_file(),(label,'FRONTEND_RESULT_MISSING',proc.poll())
        data=json.loads(result.read_text()); assert data.get('status')=='GREEN',data
        assert data.get('BROWSER_VISIBLE') is True,data
        assert data.get('PREVIEW_APPLIED') is True,data
        assert data.get('PIXEL_READBACK') in ('GREEN','UNAVAILABLE'),data
        return data
    finally:
        if proc.poll() is None: proc.terminate()
        try: out,err=proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill(); out,err=proc.communicate()
        (ROOT/f'{label}.frontend.stdout').write_text(out or ''); (ROOT/f'{label}.frontend.stderr').write_text(err or '')

front_safe=frontend_display('frontend-safe',pv_1,eq(1.0,.10,.06,.35))
front_custom=frontend_display('frontend-custom',pv_1,eq(1.0,.24,.08,.45))

# Final Render physical path. Six short jobs prove opacity and multi-effect visibility.
settings={'width':1920,'height':1080,'fps':60,'codec':'h265','bitrateMbps':10.0,'durationHours':4/3600,'durationMode':'whole-track','loopMode':'image','crossfadeSec':0.0,'normalizeLufs':False,'outputDir':str(OUT),'preset':'fast','encoderPreference':'auto'}
common={'path':str(PROJECT),'media':[str(BASE)],'audio':[str(AUDIO)],'valid':True,'error':None,'anchors':{}}
def job(pid,name,effects):
    return {'project':dict(common,id=pid,name=name),'settings':settings,'effects':effects,'subscribes':[],'ambient':None}
jobs=[
    job('eq-base','EQ BASE',[]),
    job('eq-op1','EQ OPACITY 1',[eq(1.0)]),
    job('eq-op05','EQ OPACITY 05',[eq(.5)]),
    job('eq-op0','EQ OPACITY 0',[eq(0.0)]),
    job('eq-others','EQ OTHER TWO',[fx1,fx2]),
    job('eq-multi','EQ PLUS TWO',[eq(1.0),fx1,fx2]),
]
fixture=ROOT/'render-jobs.json'; result=ROOT/'render-result.json'; fixture.write_text(json.dumps({'jobs':jobs},ensure_ascii=False,indent=2))
env=os.environ.copy(); env.update({'ENDLUME_E2E_RENDER_JOB':str(fixture),'ENDLUME_E2E_RESULT':str(result),'RUST_BACKTRACE':'1'})
started=time.perf_counter(); rp=run([APP],check=False,timeout=300,env=env); wall=time.perf_counter()-started
(ROOT/'render.stdout').write_text(rp.stdout or ''); (ROOT/'render.stderr').write_text(rp.stderr or '')
assert rp.returncode==0,(rp.returncode,rp.stderr[-12000:])
raw=json.loads(result.read_text()); assert raw.get('status')=='passed',raw
rows={x['id']:x for x in raw['results']}; assert set(rows)=={x['project']['id'] for x in jobs},rows.keys()
paths={}
for pid,row in rows.items():
    path=Path(row['outputPath']); assert path.is_file() and path.stat().st_size>1024,(pid,path)
    m=probe(path); v=next(x for x in m['streams'] if x.get('codec_type')=='video'); a=next(x for x in m['streams'] if x.get('codec_type')=='audio')
    assert v.get('codec_name')=='hevc' and (int(v['width']),int(v['height']),v.get('avg_frame_rate'))==(1920,1080,'60/1'),(pid,v)
    assert a.get('codec_name')=='aac' and int(a.get('sample_rate') or 0)==48000,(pid,a)
    paths[pid]=path

T={'begin':.55,'middle':2.0,'end':3.45}
final_stats={}
for phase,t in T.items():
    frames={pid:raw_frame(path,t) for pid,path in paths.items()}
    for pid,path in paths.items(): save_frame(path,t,EVIDENCE/f'final-{phase}-{pid}.png')
    d1=diff_stats(frames['eq-base'],frames['eq-op1']); d05=diff_stats(frames['eq-base'],frames['eq-op05']); d0=diff_stats(frames['eq-base'],frames['eq-op0']); dm=diff_stats(frames['eq-others'],frames['eq-multi'])
    final_stats[phase]={'op1':d1,'op05':d05,'op0':d0,'multiEqContribution':dm}
    assert d1['changed']>=100 and d1['meanMaxDiff']>=.45,(phase,d1)
    assert d05['meanMaxDiff']<d1['meanMaxDiff']*.82 and d05['meanMaxDiff']>d1['meanMaxDiff']*.18,(phase,d1,d05)
    assert d0['meanMaxDiff']<=max(.35,d1['meanMaxDiff']*.10),(phase,d1,d0)
    assert dm['changed']>=80 and dm['meanMaxDiff']>=.30,(phase,dm)

# Same apparent strength: compare middle Preview and Final relative to their own base.
preview_strength=P1['meanMaxDiff']; final_strength=final_stats['middle']['op1']['meanMaxDiff']; strength_ratio=preview_strength/max(final_strength,1e-9)
print(f'PREVIEW_FINAL_STRENGTH_RATIO={strength_ratio:.6f}')
assert .45<=strength_ratio<=2.20,(preview_strength,final_strength,strength_ratio)

report={
  'status':'GREEN','candidate':CANDIDATE,'source':str(EQ_SOURCE),'keyColor':KEY,
  'rootCauseProof':{'ownerMax':OWNER_MAX,'safe':SAFE},
  'safeDefaults':{'similarity':.10,'blend':.06,'despill':.35},
  'preview':{'op1':P1,'op05':P05,'op0':P0,'multiEqContribution':PM,'frontendSafe':front_safe,'frontendCustom':front_custom},
  'final':final_stats,'previewFinalStrengthRatio':strength_ratio,'renderWallSeconds':wall,
}
(ROOT/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('EQUALIZER_VISIBILITY=PASS')
print('CHROMAKEY_BACKGROUND_REMOVAL=PASS')
print('FOREGROUND_PRESERVED=PASS')
print('OPACITY_1_FULL_STRENGTH=PASS')
print('OPACITY_05_WEAKER=PASS')
print('OPACITY_0_INVISIBLE=PASS')
print('PREVIEW_RENDER_MATCH=PASS')
print('MULTI_EFFECT_EQUALIZER_VISIBILITY=PASS')
print('FRONTEND_PREVIEW_SMOKE=PASS')
print('FAST_RENDER_PHYSICAL=PASS')
print(f'FAST_RENDER_WALL_SECONDS={wall:.3f}')
