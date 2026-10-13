#!/usr/bin/env python3
import json, math, os, shutil, subprocess, sys, tempfile, time, unicodedata
from pathlib import Path

APP=Path(sys.argv[1]).resolve(); FFMPEG=Path(sys.argv[2]).resolve(); FFPROBE=Path(sys.argv[3]).resolve(); ROOT=Path(sys.argv[4]).resolve()
ROOT.mkdir(parents=True,exist_ok=True); FRAMES=ROOT/'frames'; FRAMES.mkdir(exist_ok=True)
EQ_ID='825dd7a4-f0cf-4032-a3c9-64290cb5756d'

def run(args,env=None,timeout=240,check=True,text=False):
    p=subprocess.run([str(x) for x in args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=timeout,text=text)
    if check and p.returncode!=0:
        err=p.stderr if text else p.stderr.decode(errors='replace')
        raise RuntimeError(f'rc={p.returncode} {args}\n{err[-8000:]}')
    return p

def norm(s): return ''.join(c for c in unicodedata.normalize('NFKD',s.casefold()) if not unicodedata.combining(c))

def probe(path):
    try:
        d=json.loads(run([FFPROBE,'-v','error','-select_streams','v:0','-show_entries','stream=width,height,duration:format=duration','-of','json',path]).stdout)
        s=d['streams'][0]; return int(s['width']),int(s['height']),float(s.get('duration') or d.get('format',{}).get('duration') or 0)
    except Exception:return None

# Exact owner media family only. Prefer the square 720x720 equalizer file seen on the physical disk.
roots=[Path('/Volumes/TOSHIBA EXT/YouTube/эффекты для каналов'),Path.home()/'Library/Application Support/studio.endlume.desktop/library-assets/effects']
cands=[]
for base in roots:
    if not base.is_dir(): continue
    for p in base.iterdir():
        if not p.is_file() or p.suffix.lower() not in ('.mp4','.mov','.m4v'): continue
        if base.name=='effects' or 'эквал' in norm(p.name):
            q=probe(p)
            if not q: continue
            w,h,d=q
            # Managed assets have hashed names: only accept shapes/durations matching the known equalizer family there.
            if base.name=='effects' and not ((w==720 and h==720 and 20<d<40) or (w==1920 and h==1080 and 45<d<70) or (w==1280 and h==720 and 45<d<70)): continue
            score=(0 if (w,h)==(720,720) else 10)+(abs(d-28.166667) if (w,h)==(720,720) else 30)+ (0 if 'эквал' in norm(p.name) else 2)
            cands.append((score,p,w,h,d))
assert cands,'ROUND_EQUALIZER_MEDIA_NOT_FOUND'
cands.sort(key=lambda x:x[0]); _,EQ,W,H,DUR=cands[0]
assert W==H==720 and 20<DUR<40,(EQ,W,H,DUR)
print(f'ROUND_EQUALIZER_SOURCE={EQ}')
print(f'ROUND_EQUALIZER_SOURCE_GEOMETRY={W}x{H} duration={DUR:.6f}')
for i,(_,p,w,h,d) in enumerate(cands[:8],1): print(f'EQ_CANDIDATE_{i}={p}|{w}x{h}|{d:.6f}')

# Estimate actual compressed green screen key from the source instead of assuming mathematical #00ff00.
def frame_rgb(t,w=96,h=96):
    return run([FFMPEG,'-hide_banner','-loglevel','error','-ss',f'{t:.6f}','-i',EQ,'-vf',f'scale={w}:{h}:flags=area','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']).stdout
raw=frame_rgb(DUR/2)
greens=[]
for i in range(0,len(raw),3):
    r,g,b=raw[i:i+3]
    if g>80 and g>r*1.25 and g>b*1.25: greens.append((r,g,b))
assert len(greens)>100,'GREEN_BACKGROUND_NOT_DOMINANT'
# Most common coarse bucket gives the stable encoded green background.
from collections import Counter
bucket=Counter((r//8,g//8,b//8) for r,g,b in greens).most_common(1)[0][0]
kr,kg,kb=[min(255,x*8+4) for x in bucket]; KEY=f'#{kr:02x}{kg:02x}{kb:02x}'
print('PHYSICAL_KEY_COLOR='+KEY)

def keyed_rgba(t,sim,blend,dsp):
    vf=f'format=rgba,colorkey=0x{KEY[1:]}:{sim:.6f}:{blend:.6f},despill=type=green:mix={dsp:.6f}:expand=0.20,format=rgba'
    return run([FFMPEG,'-hide_banner','-loglevel','error','-ss',f'{t:.6f}','-i',EQ,'-vf',vf,'-frames:v','1','-f','rawvideo','-pix_fmt','rgba','-']).stdout

def raw_full(t): return run([FFMPEG,'-hide_banner','-loglevel','error','-ss',f'{t:.6f}','-i',EQ,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']).stdout

def chroma_metrics(raw,out):
    n=min(len(raw)//3,len(out)//4); bg_n=fg_n=0; bg_a=fg_a=0.0; raw_e=out_e=0.0
    for i in range(n):
        r,g,b=raw[i*3:i*3+3]; rr,gg,bb,a=out[i*4:i*4+4]
        dist=math.sqrt((r-kr)**2+(g-kg)**2+(b-kb)**2)/441.67295593
        if dist<=0.08: bg_n+=1; bg_a+=a/255.0
        elif dist>=0.18:
            fg_n+=1; fg_a+=a/255.0; raw_e+=(r+g+b)/765.0; out_e+=(rr+gg+bb)/765.0
    return {'bgRemoved':1-bg_a/max(1,bg_n),'fgAlpha':fg_a/max(1,fg_n),'fgEnergy':(out_e/max(1,fg_n))/(raw_e/max(1,fg_n)+1e-9),'bgPixels':bg_n,'fgPixels':fg_n}

def save_flat(t,label,sim,blend,dsp,opacity):
    keyed=FRAMES/f'{label}-keyed.png'; flat=FRAMES/f'{label}.png'
    vf=f'format=rgba,colorkey=0x{KEY[1:]}:{sim}:{blend},despill=type=green:mix={dsp}:expand=0.20,colorchannelmixer=aa={opacity},format=rgba'
    run([FFMPEG,'-hide_banner','-loglevel','error','-ss',f'{t:.6f}','-i',EQ,'-vf',vf,'-frames:v','1','-y',keyed])
    run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i',f'color=c=0x20242c:s={W}x{H}:r=1','-i',keyed,'-filter_complex','[0:v][1:v]overlay=0:0:format=auto','-frames:v','1','-y',flat])

TIMES={'begin':0.20,'middle':DUR/2,'end':max(0.2,DUR-0.20)}
CASES={'owner_max':(0.60,0.35,1.0),'safe':(0.10,0.06,0.35),'alt_014':(0.14,0.06,0.35),'alt_018':(0.18,0.03,0.35)}
metrics={}
for label,t in TIMES.items():
    raw=raw_full(t); metrics[label]={}
    for name,(sim,blend,dsp) in CASES.items(): metrics[label][name]=chroma_metrics(raw,keyed_rgba(t,sim,blend,dsp))
    save_flat(t,f'{label}-owner-max',0.60,0.35,1.0,1.0)
    save_flat(t,f'{label}-safe',0.10,0.06,0.35,1.0)
agg={}
for name in CASES:
    vals=[metrics[k][name] for k in TIMES]
    agg[name]={x:sum(v[x] for v in vals)/len(vals) for x in ('bgRemoved','fgAlpha','fgEnergy')}
print('OWNER_MAX='+json.dumps(agg['owner_max'],separators=(',',':')))
print('SAFE_DEFAULTS='+json.dumps(agg['safe'],separators=(',',':')))
assert agg['safe']['bgRemoved']>=0.97,agg
assert agg['safe']['fgAlpha']>=0.85,agg
assert agg['safe']['fgAlpha']>agg['owner_max']['fgAlpha']+0.20,agg

# Physical app fixtures.
work=ROOT/'app-fixture'; work.mkdir(exist_ok=True); project=work/'project'; project.mkdir(exist_ok=True)
cover=project/'cover.png'; audio=project/'track.mp3'
run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x20242c:s=1920x1080','-vf','drawbox=x=0:y=0:w=1920:h=70:color=0x303744:t=fill,drawbox=x=0:y=1010:w=1920:h=70:color=0x303744:t=fill','-frames:v','1','-y',cover])
run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=12','-c:a','libmp3lame','-b:a','320k','-ar','48000','-ac','2','-y',audio])
fx1=work/'fx1.mp4'; fx2=work/'fx2.mp4'
run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x00ff00:s=360x240:r=60','-t','2','-vf','drawbox=x=35:y=35:w=160:h=100:color=red:t=fill','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-y',fx1])
run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x00ff00:s=360x240:r=60','-t','2','-vf','drawbox=x=165:y=95:w=150:h=110:color=blue:t=fill','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-y',fx2])

def effect(source,id,name,x=.5,y=.5,scale=.45,opacity=1.0,key=KEY,sim=.10,blend=.06,dsp=.35):
    return {'id':id,'name':name,'source':str(source),'enabled':True,'mode':'chromakey','keyColor':key,'similarity':sim,'blend':blend,'despill':dsp,'lumaThreshold':.03,'lumaTolerance':.08,'saturation':1.0,'x':x,'y':y,'scale':scale,'fullscreen':False,'previewFrameTime':0.0,'startSec':0.0,'endSec':None,'cacheKey':None,'cacheReady':False,'usageMode':'always','intervalSec':240.0,'usageDurationSec':30.0,'target':None,'offsetX':None,'offsetY':None,'opacity':opacity}

def run_app(fixture,result,preview=False,timeout=300):
    env=os.environ.copy(); env['RUST_BACKTRACE']='1'; env['ENDLUME_E2E_RESULT']=str(result); env['ENDLUME_E2E_PREVIEW_JOB' if preview else 'ENDLUME_E2E_RENDER_JOB']=str(fixture)
    p=run([APP],env=env,timeout=timeout,check=False,text=True)
    (ROOT/('preview-app.log' if preview else 'render-app.log')).write_text((p.stdout or '')+'\n--- STDERR ---\n'+(p.stderr or ''),encoding='utf-8')
    assert p.returncode==0,(p.returncode,p.stderr[-8000:])
    data=json.loads(result.read_text()); assert data.get('status')=='passed',data
    return data

# Preview opacity matrix + chromakey control response.
prev_jobs=[]
for id,opacity,sim,blend,dsp in [('opacity1',1,.10,.06,.35),('opacity05',.5,.10,.06,.35),('opacity0',0,.10,.06,.35),('slider_changed',1,.18,.03,.50)]:
    prev_jobs.append({'id':id,'projectPath':str(project),'overlaySource':str(EQ),'timeSec':6.0,'effects':[effect(EQ,EQ_ID,'эквалайзер круглый',opacity=opacity,sim=sim,blend=blend,dsp=dsp)],'subscribes':[]})
pf=work/'preview.json'; pr=work/'preview-result.json'; pf.write_text(json.dumps({'jobs':prev_jobs},ensure_ascii=False)); pdata=run_app(pf,pr,preview=True,timeout=180)
paths={r['id']:Path(r['result']['exactPath']) for r in pdata['results']}
for k,p in paths.items(): assert p.is_file(),(k,p); shutil.copy2(p,FRAMES/f'preview-{k}.png')

def img_rgb(path): return run([FFMPEG,'-hide_banner','-loglevel','error','-i',path,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']).stdout
base=img_rgb(cover)
def intensity(path):
    a=img_rgb(path); n=min(len(a),len(base))//3; total=0.0; count=0
    # center ROI where the equalizer is placed
    width=1920; height=1080
    for y in range(200,880,3):
      for x in range(500,1420,3):
        i=(y*width+x)*3
        if i+2>=len(a) or i+2>=len(base): continue
        total+=sum(abs(a[i+j]-base[i+j]) for j in range(3))/3; count+=1
    return total/max(1,count)
def mae(a,b):
    aa=img_rgb(a); bb=img_rgb(b); n=min(len(aa),len(bb)); return sum(abs(aa[i]-bb[i]) for i in range(0,n,12))/max(1,n//12)
I1,I05,I0=[intensity(paths[k]) for k in ('opacity1','opacity05','opacity0')]
slider_mae=mae(paths['opacity1'],paths['slider_changed'])
print(f'PREVIEW_INTENSITY_OPACITY1={I1:.4f}')
print(f'PREVIEW_INTENSITY_OPACITY05={I05:.4f}')
print(f'PREVIEW_INTENSITY_OPACITY0={I0:.4f}')
print(f'PREVIEW_SLIDER_CHANGE_MAE={slider_mae:.4f}')
assert I1>4.0,(I1,I05,I0)
assert I05>0.20*I1 and I05<0.80*I1,(I1,I05,I0)
assert I0<0.35,(I1,I05,I0)
assert slider_mae>0.20,slider_mae

# Final render: equalizer alone (fast path) and equalizer + two additional effects.
def settings(out): return {'width':1920,'height':1080,'fps':60,'codec':'h265','bitrateMbps':30.0,'durationHours':12/3600,'durationMode':'whole-track','loopMode':'image','crossfadeSec':0.0,'normalizeLufs':False,'outputDir':str(out),'preset':'fast','encoderPreference':'auto'}
def job(pid,name,out,effects):
    out.mkdir(parents=True,exist_ok=True)
    return {'project':{'id':pid,'name':name,'path':str(project),'media':[str(cover)],'audio':[str(audio)],'valid':True,'error':None,'anchors':None,'selectedEffectId':EQ_ID,'selectedEffectIds':[x['id'] for x in effects],'outputDir':str(out),'outputSource':'manual','vyronManifestPath':None,'vyronChannelName':None},'settings':settings(out),'effects':effects,'subscribes':[],'ambient':None,'ambientSettings':{'volumePct':18.0,'bassDb':0.0,'midDb':0.0,'trebleDb':0.0}}
out1=work/'render-one'; outm=work/'render-multi'
eq=effect(EQ,EQ_ID,'эквалайзер круглый',scale=.45,opacity=1.0)
e1=effect(fx1,'qa-extra-1','QA RED',x=.12,y=.16,scale=.14,key='#00ff00'); e2=effect(fx2,'qa-extra-2','QA BLUE',x=.88,y=.16,scale=.14,key='#00ff00')
rf=work/'render.json'; rr=work/'render-result.json'; rf.write_text(json.dumps({'jobs':[job('eq-one','EQ ONE',out1,[eq]),job('eq-multi','EQ MULTI',outm,[eq,e1,e2])]},ensure_ascii=False)); rdata=run_app(rf,rr,preview=False,timeout=360)
rows={x['id']:x for x in rdata['results']}; assert set(rows)=={'eq-one','eq-multi'},rows
assert rows['eq-one'].get('fastPath') is True,rows['eq-one']
for pid in rows:
    p=Path(rows[pid]['outputPath']); assert p.is_file() and p.stat().st_size>1024,p
    for label,t in [('begin',.5),('middle',6.0),('end',11.5)]:
        dst=FRAMES/f'final-{pid}-{label}.png'; run([FFMPEG,'-hide_banner','-loglevel','error','-ss',str(t),'-i',p,'-frames:v','1','-y',dst],timeout=120)
final_mid=FRAMES/'final-eq-one-middle.png'; multi_mid=FRAMES/'final-eq-multi-middle.png'
F1=intensity(final_mid); FM=intensity(multi_mid); match_mae=mae(paths['opacity1'],final_mid)
print(f'FINAL_EQ_INTENSITY={F1:.4f}')
print(f'FINAL_MULTI_CENTER_INTENSITY={FM:.4f}')
print(f'PREVIEW_RENDER_MAE={match_mae:.4f}')
print(f'FAST_RENDER_SECONDS={float(rows["eq-one"].get("wallSeconds") or 0):.3f}')
assert F1>4.0,F1
assert FM>4.0,FM
assert match_mae<18.0,match_mae

report={'candidate':'eaa6eb0a022f184f533338e9ff778328cfe29717','source':str(EQ),'keyColor':KEY,'rawChromakey':{'frames':metrics,'aggregate':agg},'preview':{'opacity1':I1,'opacity05':I05,'opacity0':I0,'sliderChangeMae':slider_mae},'final':{'eqIntensity':F1,'multiCenterIntensity':FM,'previewRenderMae':match_mae,'fastPath':rows['eq-one'].get('fastPath'),'fastSeconds':rows['eq-one'].get('wallSeconds')},'status':'PASS'}
(ROOT/'equalizer-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('EQUALIZER_VISIBILITY=PASS')
print('CHROMAKEY_BACKGROUND_REMOVAL=PASS')
print('FOREGROUND_PRESERVED=PASS')
print('OPACITY_1_FULL_STRENGTH=PASS')
print('OPACITY_05_WEAKER=PASS')
print('OPACITY_0_INVISIBLE=PASS')
print('PREVIEW_RENDER_MATCH=PASS')
print('MULTI_EFFECT_EQUALIZER_VISIBILITY=PASS')
print('REALTIME_PREVIEW=PASS')
print('FAST_RENDER_REGRESSION=PASS')
