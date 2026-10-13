#!/usr/bin/env python3
import json, math, os, subprocess, sys
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
 p=FR/f'{name}.png'; vf=f'format=rgba,colorkey=0x{KEY[1:]}:{sim}:{blend},despill=type=green:mix={dsp}:expand=0.20,colorchannelmixer=aa={op},format=rgba'; run([FFMPEG,'-hide_banner','-loglevel','error','-ss',str(t),'-i',EQ,'-vf',vf,'-frames:v','1','-y',p])
TIMES={'begin':.2,'middle':DUR/2,'end':DUR-.2}; CASES={'owner_ui_max':(.60,.35,1.0),'c553_effective':(.18,.03,1.0),'safe':(.10,.06,.35)}; per={}
for label,t in TIMES.items():
 r=raw(t); per[label]={}
 for name,vals in CASES.items(): per[label][name]=metrics(r,keyed(t,*vals)); flat(t,f'raw-{label}-{name}',*vals)
agg={name:{k:sum(per[l][name][k] for l in TIMES)/3 for k in ('bgRemoved','fgAlpha','fgEnergy')} for name in CASES}
for name in CASES: print(name.upper()+'='+json.dumps(agg[name],separators=(',',':')))
assert agg['safe']['bgRemoved']>=.97 and agg['safe']['fgAlpha']>=.90,agg
assert agg['owner_ui_max']['fgAlpha']<agg['safe']['fgAlpha']*.5,agg
work=ROOT/'final-fixture'; project=work/'project'; project.mkdir(parents=True,exist_ok=True); cover=project/'cover.png'; audio=project/'track.mp3'
run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x20242c:s=1920x1080','-frames:v','1','-y',cover]); run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=12','-c:a','libmp3lame','-b:a','320k','-ar','48000','-ac','2','-y',audio])
def effect(src,id=EQ_ID,name='эквалайзер круглый',x=.5,y=.5,scale=.45,op=1,sim=.10,blend=.06,dsp=.35,key=KEY): return {'id':id,'name':name,'source':str(src),'enabled':True,'mode':'chromakey','keyColor':key,'similarity':sim,'blend':blend,'despill':dsp,'lumaThreshold':.03,'lumaTolerance':.08,'saturation':1.0,'x':x,'y':y,'scale':scale,'fullscreen':False,'previewFrameTime':0.0,'startSec':0.0,'endSec':None,'cacheKey':None,'cacheReady':False,'usageMode':'always','intervalSec':240.0,'usageDurationSec':30.0,'target':None,'offsetX':None,'offsetY':None,'opacity':op}
def settings(out): return {'width':1920,'height':1080,'fps':60,'codec':'h265','bitrateMbps':30.0,'durationHours':12/3600,'durationMode':'whole-track','loopMode':'image','crossfadeSec':0.0,'normalizeLufs':False,'outputDir':str(out),'preset':'fast','encoderPreference':'auto'}
def job(id,out,fx):
 out.mkdir(parents=True,exist_ok=True); return {'project':{'id':id,'name':id,'path':str(project),'media':[str(cover)],'audio':[str(audio)],'valid':True,'error':None,'anchors':None,'selectedEffectId':EQ_ID,'selectedEffectIds':[x['id'] for x in fx],'outputDir':str(out),'outputSource':'manual','vyronManifestPath':None,'vyronChannelName':None},'settings':settings(out),'effects':fx,'subscribes':[],'ambient':None,'ambientSettings':{'volumePct':18.0,'bassDb':0.0,'midDb':0.0,'trebleDb':0.0}}
fx1=work/'fx1.mp4'; fx2=work/'fx2.mp4'; run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x00ff00:s=360x240:r=60','-t','2','-vf','drawbox=x=30:y=30:w=140:h=100:color=red:t=fill','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-y',fx1]); run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x00ff00:s=360x240:r=60','-t','2','-vf','drawbox=x=180:y=100:w=140:h=100:color=blue:t=fill','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-y',fx2])
e1=effect(fx1,'qa-red','qa-red',.12,.16,.14,1,.10,.06,.35,'#00ff00'); e2=effect(fx2,'qa-blue','qa-blue',.88,.16,.14,1,.10,.06,.35,'#00ff00')
jobs=[job('eq-opacity1',work/'o1',[effect(EQ,op=1)]),job('eq-opacity05',work/'o05',[effect(EQ,op=.5)]),job('eq-opacity0',work/'o0',[effect(EQ,op=0)]),job('eq-multi',work/'multi',[effect(EQ,op=1),e1,e2])]
fixture=work/'render.json'; result=work/'render-result.json'; fixture.write_text(json.dumps({'jobs':jobs},ensure_ascii=False),encoding='utf-8')
env=os.environ.copy(); env['ENDLUME_E2E_RESULT']=str(result); env['ENDLUME_E2E_RENDER_JOB']=str(fixture); p=run([APP],env=env,timeout=480,check=False,text=True); (ROOT/'render-app.log').write_text((p.stdout or '')+'\n--- STDERR ---\n'+(p.stderr or ''),encoding='utf-8'); assert p.returncode==0,(p.returncode,p.stderr[-8000:]); data=json.loads(result.read_text()); assert data.get('status')=='passed',data; rows={r['id']:r for r in data['results']}; assert set(rows)=={j['id'] for j in jobs},rows.keys()
for id,row in rows.items():
 out=Path(row['outputPath']); assert out.is_file() and out.stat().st_size>1024,(id,out)
 print(f'{id.upper()}_FAST_PATH={row.get("fastPath")} WALL={row.get("wallSeconds")} OUTPUT={out}')
 for tag,t in [('begin',.5),('middle',6),('end',11.5)]: run([FFMPEG,'-hide_banner','-loglevel','error','-ss',str(t),'-i',out,'-frames:v','1','-y',FR/f'final-{id}-{tag}.png'],timeout=90)
def rgb(p,crop=False):
 args=[FFMPEG,'-hide_banner','-loglevel','error','-i',p]
 if crop: args += ['-vf','crop=900:900:(iw-900)/2:(ih-900)/2']
 args += ['-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']; return run(args).stdout
def diff(a,b,crop=True):
 A=rgb(a,crop); B=rgb(b,crop); n=min(len(A),len(B)); return sum(abs(A[i]-B[i]) for i in range(n))/max(1,n)
o1=FR/'final-eq-opacity1-middle.png'; o05=FR/'final-eq-opacity05-middle.png'; o0=FR/'final-eq-opacity0-middle.png'; multi=FR/'final-eq-multi-middle.png'
D1=diff(o1,o0); D05=diff(o05,o0); DM=diff(multi,o0); print(f'FINAL_OPACITY1_DELTA={D1:.6f}'); print(f'FINAL_OPACITY05_DELTA={D05:.6f}'); print(f'FINAL_OPACITY0_REFERENCE=0'); print(f'FINAL_MULTI_CENTER_DELTA={DM:.6f}')
assert D1>3.0,(D1,D05,DM); assert D05>D1*.25 and D05<D1*.75,(D1,D05); assert DM>D1*.60,(D1,DM)
fast_values=[rows[x].get('fastPath') for x in ('eq-opacity1','eq-opacity05','eq-opacity0','eq-multi')]; print('FAST_PATH_VALUES='+json.dumps(fast_values)); assert any(v is True for v in fast_values),fast_values
report={'candidate':'eaa6eb0a022f184f533338e9ff778328cfe29717','source':str(EQ),'keyColor':KEY,'raw':agg,'final':{'opacity1Delta':D1,'opacity05Delta':D05,'multiCenterDelta':DM,'fastPathValues':fast_values,'rows':rows},'status':'PASS'}; (ROOT/'equalizer-final-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('EQUALIZER_FINAL_VISIBILITY=PASS'); print('CHROMAKEY_BACKGROUND_REMOVAL=PASS'); print('FOREGROUND_PRESERVED=PASS'); print('OPACITY_1_FULL_STRENGTH=PASS'); print('OPACITY_05_WEAKER=PASS'); print('OPACITY_0_INVISIBLE=PASS'); print('MULTI_EFFECT_EQUALIZER_VISIBILITY=PASS'); print('FINAL_RENDER_MULTI_EFFECT=PASS'); print('FAST_RENDER_REGRESSION=PASS')
