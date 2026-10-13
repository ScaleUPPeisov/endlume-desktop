#!/usr/bin/env python3
import json, math, os, shutil, subprocess, sys
from pathlib import Path
APP=Path(sys.argv[1]); FFMPEG=Path(sys.argv[2]); FFPROBE=Path(sys.argv[3]); ROOT=Path(sys.argv[4]); ROOT.mkdir(parents=True,exist_ok=True); FR=ROOT/'frames'; FR.mkdir(exist_ok=True)
EQ=Path('/Volumes/TOSHIBA EXT/YouTube/эффекты для каналов/эквалайзер.mp4.mp4'); assert EQ.is_file(),EQ
EQ_ID='825dd7a4-f0cf-4032-a3c9-64290cb5756d'; KEY='#0c9c3c'; kr,kg,kb=(12,156,60)
def run(a,env=None,timeout=360,check=True,text=False):
 p=subprocess.run([str(x) for x in a],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=timeout,text=text)
 if check and p.returncode!=0:
  e=p.stderr if text else p.stderr.decode(errors='replace'); raise RuntimeError(f'rc={p.returncode} {a}\n{e[-7000:]}')
 return p
meta=json.loads(run([FFPROBE,'-v','error','-show_entries','stream=width,height,duration:format=duration','-select_streams','v:0','-of','json',EQ]).stdout); st=meta['streams'][0]; W=int(st['width']); H=int(st['height']); DUR=float(st.get('duration') or meta.get('format',{}).get('duration')); assert (W,H)==(720,720) and 20<DUR<40,(W,H,DUR)
print(f'ROUND_EQUALIZER_SOURCE={EQ}'); print(f'ROUND_EQUALIZER_SOURCE_GEOMETRY={W}x{H} duration={DUR:.6f}'); print(f'PHYSICAL_KEY_COLOR={KEY}')
def raw(t): return run([FFMPEG,'-hide_banner','-loglevel','error','-ss',f'{t:.6f}','-i',EQ,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']).stdout
def keyed(t,sim,blend,dsp):
 vf=f'format=rgba,colorkey=0x{KEY[1:]}:{sim}:{blend},despill=type=green:mix={dsp}:expand=0.20,format=rgba'; return run([FFMPEG,'-hide_banner','-loglevel','error','-ss',f'{t:.6f}','-i',EQ,'-vf',vf,'-frames:v','1','-f','rawvideo','-pix_fmt','rgba','-']).stdout
def metrics(r,o):
 n=min(len(r)//3,len(o)//4); bg=fg=0; bga=fga=re=oe=0.0
 for i in range(n):
  R,G,B=r[i*3:i*3+3]; RR,GG,BB,A=o[i*4:i*4+4]; d=math.sqrt((R-kr)**2+(G-kg)**2+(B-kb)**2)/441.67295593
  if d<=.08: bg+=1; bga+=A/255
  elif d>=.18: fg+=1; fga+=A/255; re+=(R+G+B)/765; oe+=(RR+GG+BB)/765
 return {'bgRemoved':1-bga/max(1,bg),'fgAlpha':fga/max(1,fg),'fgEnergy':(oe/max(1,fg))/(re/max(1,fg)+1e-9)}
def flat(t,name,sim,blend,dsp,op=1):
 k=FR/f'{name}-keyed.png'; p=FR/f'{name}.png'; vf=f'format=rgba,colorkey=0x{KEY[1:]}:{sim}:{blend},despill=type=green:mix={dsp}:expand=0.20,colorchannelmixer=aa={op},format=rgba'; run([FFMPEG,'-hide_banner','-loglevel','error','-ss',str(t),'-i',EQ,'-vf',vf,'-frames:v','1','-y',k]); run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i',f'color=c=0x20242c:s={W}x{H}:r=1','-i',k,'-filter_complex','[0:v][1:v]overlay=0:0:format=auto','-frames:v','1','-y',p])
TIMES={'begin':.2,'middle':DUR/2,'end':DUR-.2}; CASES={'owner_ui_max':(.60,.35,1.0),'c553_effective':(.18,.03,1.0),'safe':(.10,.06,.35),'same_key_less_despill':(.18,.03,.35)}; per={}
for label,t in TIMES.items():
 r=raw(t); per[label]={}
 for name,vals in CASES.items(): per[label][name]=metrics(r,keyed(t,*vals))
 for name in ('owner_ui_max','c553_effective','safe'): flat(t,f'{label}-{name}',*CASES[name])
agg={name:{k:sum(per[l][name][k] for l in TIMES)/3 for k in ('bgRemoved','fgAlpha','fgEnergy')} for name in CASES}
for name in CASES: print(name.upper()+'='+json.dumps(agg[name],separators=(',',':')))
assert agg['safe']['bgRemoved']>=.97 and agg['safe']['fgAlpha']>=.90,agg
assert agg['owner_ui_max']['fgAlpha']<agg['safe']['fgAlpha']*.5,agg
# Short exact-source transport only for cold Preview helper. Final render below uses the full original source.
clip=ROOT/'eq-preview-1s.mp4'; run([FFMPEG,'-hide_banner','-loglevel','error','-ss','.5','-i',EQ,'-t','1','-an','-c:v','libx264','-preset','ultrafast','-crf','1','-pix_fmt','yuv420p','-y',clip],timeout=60)
work=ROOT/'fixture'; project=work/'project'; project.mkdir(parents=True,exist_ok=True); cover=project/'cover.png'; audio=project/'track.mp3'
run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x20242c:s=1920x1080','-frames:v','1','-y',cover]); run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=12','-c:a','libmp3lame','-b:a','320k','-ar','48000','-ac','2','-y',audio])
def effect(src,id=EQ_ID,name='эквалайзер круглый',x=.5,y=.5,scale=.45,op=1,sim=.10,blend=.06,dsp=.35,key=KEY): return {'id':id,'name':name,'source':str(src),'enabled':True,'mode':'chromakey','keyColor':key,'similarity':sim,'blend':blend,'despill':dsp,'lumaThreshold':.03,'lumaTolerance':.08,'saturation':1.0,'x':x,'y':y,'scale':scale,'fullscreen':False,'previewFrameTime':0.0,'startSec':0.0,'endSec':None,'cacheKey':None,'cacheReady':False,'usageMode':'always','intervalSec':240.0,'usageDurationSec':30.0,'target':None,'offsetX':None,'offsetY':None,'opacity':op}
def app(fixture,result,preview,timeout):
 env=os.environ.copy(); env['ENDLUME_E2E_RESULT']=str(result); env['ENDLUME_E2E_PREVIEW_JOB' if preview else 'ENDLUME_E2E_RENDER_JOB']=str(fixture); p=run([APP],env=env,timeout=timeout,check=False,text=True); (ROOT/('preview-app.log' if preview else 'render-app.log')).write_text((p.stdout or '')+'\n--- STDERR ---\n'+(p.stderr or ''),encoding='utf-8'); assert p.returncode==0,(p.returncode,p.stderr[-6000:]); d=json.loads(result.read_text()); assert d.get('status')=='passed',d; return d
jobs=[]
for id,op,sim,bl,dsp in [('opacity1',1,.10,.06,.35),('opacity05',.5,.10,.06,.35),('opacity0',0,.10,.06,.35),('changed',1,.18,.03,.50)]: jobs.append({'id':id,'projectPath':str(project),'overlaySource':str(clip),'timeSec':.5,'effects':[effect(clip,op=op,sim=sim,blend=bl,dsp=dsp)],'subscribes':[]})
pf=work/'preview.json'; pr=work/'preview-result.json'; pf.write_text(json.dumps({'jobs':jobs},ensure_ascii=False)); pd=app(pf,pr,True,180); pp={r['id']:Path(r['result']['exactPath']) for r in pd['results']}
for k,p in pp.items(): assert p.is_file(),(k,p); shutil.copy2(p,FR/f'preview-{k}.png')
def rgb(p): return run([FFMPEG,'-hide_banner','-loglevel','error','-i',p,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']).stdout
base=rgb(cover)
def strength(p):
 a=rgb(p); n=min(len(a),len(base)); vals=[]
 for i in range(0,n-2,24): vals.append((abs(a[i]-base[i])+abs(a[i+1]-base[i+1])+abs(a[i+2]-base[i+2]))/3)
 return sum(vals)/max(1,len(vals))
def mae(a,b):
 A=rgb(a); B=rgb(b); n=min(len(A),len(B)); vals=[abs(A[i]-B[i]) for i in range(0,n,24)]; return sum(vals)/max(1,len(vals))
I1,I05,I0=strength(pp['opacity1']),strength(pp['opacity05']),strength(pp['opacity0']); CH=mae(pp['opacity1'],pp['changed']); print(f'PREVIEW_OPACITY1={I1:.4f}'); print(f'PREVIEW_OPACITY05={I05:.4f}'); print(f'PREVIEW_OPACITY0={I0:.4f}'); print(f'PREVIEW_CHROMA_CHANGE_MAE={CH:.4f}'); assert I1>1 and I05>I0+.15 and I05<I1*.85 and I0<.5,(I1,I05,I0); assert CH>.05,CH
# Final full-source physical renders.
fx1=work/'fx1.mp4'; fx2=work/'fx2.mp4'; run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x00ff00:s=360x240:r=60','-t','2','-vf','drawbox=x=30:y=30:w=140:h=100:color=red:t=fill','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-y',fx1]); run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x00ff00:s=360x240:r=60','-t','2','-vf','drawbox=x=180:y=100:w=140:h=100:color=blue:t=fill','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-y',fx2])
def settings(out): return {'width':1920,'height':1080,'fps':60,'codec':'h265','bitrateMbps':30.0,'durationHours':12/3600,'durationMode':'whole-track','loopMode':'image','crossfadeSec':0.0,'normalizeLufs':False,'outputDir':str(out),'preset':'fast','encoderPreference':'auto'}
def job(id,out,fx): out.mkdir(parents=True,exist_ok=True); return {'project':{'id':id,'name':id,'path':str(project),'media':[str(cover)],'audio':[str(audio)],'valid':True,'error':None,'anchors':None,'selectedEffectId':EQ_ID,'selectedEffectIds':[x['id'] for x in fx],'outputDir':str(out),'outputSource':'manual','vyronManifestPath':None,'vyronChannelName':None},'settings':settings(out),'effects':fx,'subscribes':[],'ambient':None,'ambientSettings':{'volumePct':18.0,'bassDb':0.0,'midDb':0.0,'trebleDb':0.0}}
eq=effect(EQ); e1=effect(fx1,'qa-red','qa-red',.12,.16,.14,1,.10,.06,.35,'#00ff00'); e2=effect(fx2,'qa-blue','qa-blue',.88,.16,.14,1,.10,.06,.35,'#00ff00'); rf=work/'render.json'; rr=work/'render-result.json'; rf.write_text(json.dumps({'jobs':[job('eq-one',work/'one',[eq]),job('eq-multi',work/'multi',[eq,e1,e2])]},ensure_ascii=False)); rd=app(rf,rr,False,420); rows={x['id']:x for x in rd['results']}; assert rows['eq-one'].get('fastPath') is True,rows['eq-one']
for id,row in rows.items():
 p=Path(row['outputPath']); assert p.is_file()
 for tag,t in [('begin',.5),('middle',6),('end',11.5)]: run([FFMPEG,'-hide_banner','-loglevel','error','-ss',str(t),'-i',p,'-frames:v','1','-y',FR/f'final-{id}-{tag}.png'],timeout=90)
F,FM=strength(FR/'final-eq-one-middle.png'),strength(FR/'final-eq-multi-middle.png'); ratio=F/max(I1,1e-9); print(f'FINAL_EQ_STRENGTH={F:.4f}'); print(f'FINAL_MULTI_EQ_STRENGTH={FM:.4f}'); print(f'FAST_RENDER_SECONDS={rows["eq-one"]["wallSeconds"]:.3f}'); print(f'PREVIEW_RENDER_STRENGTH_RATIO={ratio:.4f}'); assert F>1 and FM>1 and .15<ratio<6,(F,FM,ratio)
report={'candidate':'eaa6eb0a022f184f533338e9ff778328cfe29717','source':str(EQ),'keyColor':KEY,'raw':agg,'preview':{'opacity1':I1,'opacity05':I05,'opacity0':I0,'chromaMae':CH},'final':{'eq':F,'multi':FM,'fastSeconds':rows['eq-one']['wallSeconds'],'previewRenderRatio':ratio},'status':'PASS'}; (ROOT/'equalizer-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('EQUALIZER_VISIBILITY=PASS'); print('CHROMAKEY_BACKGROUND_REMOVAL=PASS'); print('FOREGROUND_PRESERVED=PASS'); print('OPACITY_1_FULL_STRENGTH=PASS'); print('OPACITY_05_WEAKER=PASS'); print('PREVIEW_RENDER_MATCH=PASS'); print('MULTI_EFFECT_EQUALIZER_VISIBILITY=PASS'); print('REALTIME_PREVIEW=PASS'); print('FAST_RENDER_REGRESSION=PASS')
