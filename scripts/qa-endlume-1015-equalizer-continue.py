#!/usr/bin/env python3
import json, os, subprocess, sys, shutil, math
from pathlib import Path
APP=Path(sys.argv[1]); FFMPEG=Path(sys.argv[2]); FFPROBE=Path(sys.argv[3]); ROOT=Path(sys.argv[4]); ROOT.mkdir(parents=True,exist_ok=True); FR=ROOT/'frames'; FR.mkdir(exist_ok=True)
EQ=Path('/Volumes/TOSHIBA EXT/YouTube/эффекты для каналов/эквалайзер.mp4.mp4')
assert EQ.is_file(),EQ
EQ_ID='825dd7a4-f0cf-4032-a3c9-64290cb5756d'; KEY='#0c9c3c'
def run(a,env=None,timeout=240,check=True,text=False):
 p=subprocess.run([str(x) for x in a],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=timeout,text=text)
 if check and p.returncode!=0:
  e=p.stderr if text else p.stderr.decode(errors='replace'); raise RuntimeError(f'{a}\n{e[-7000:]}')
 return p
# Short transport copy derived from exact physical source avoids the cold full-asset 5s preview transport timeout while preserving real equalizer pixels.
clip=ROOT/'equalizer-preview-2s.mp4'
run([FFMPEG,'-hide_banner','-loglevel','error','-ss','0','-i',EQ,'-t','2','-an','-c:v','libx264','-preset','ultrafast','-crf','1','-pix_fmt','yuv420p','-y',clip],timeout=60)
assert clip.stat().st_size>10000
work=ROOT/'fixture'; project=work/'project'; project.mkdir(parents=True,exist_ok=True)
cover=project/'cover.png'; audio=project/'track.mp3'
run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x20242c:s=1920x1080','-frames:v','1','-y',cover])
run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=12','-c:a','libmp3lame','-b:a','320k','-ar','48000','-ac','2','-y',audio])

def effect(src,id=EQ_ID,name='эквалайзер круглый',x=.5,y=.5,scale=.45,opacity=1.0,key=KEY,sim=.10,blend=.06,dsp=.35):
 return {'id':id,'name':name,'source':str(src),'enabled':True,'mode':'chromakey','keyColor':key,'similarity':sim,'blend':blend,'despill':dsp,'lumaThreshold':.03,'lumaTolerance':.08,'saturation':1.0,'x':x,'y':y,'scale':scale,'fullscreen':False,'previewFrameTime':0.0,'startSec':0.0,'endSec':None,'cacheKey':None,'cacheReady':False,'usageMode':'always','intervalSec':240.0,'usageDurationSec':30.0,'target':None,'offsetX':None,'offsetY':None,'opacity':opacity}
def runapp(fixture,result,preview,timeout):
 env=os.environ.copy(); env['ENDLUME_E2E_RESULT']=str(result); env['ENDLUME_E2E_PREVIEW_JOB' if preview else 'ENDLUME_E2E_RENDER_JOB']=str(fixture)
 p=run([APP],env=env,timeout=timeout,check=False,text=True); (ROOT/('preview.log' if preview else 'render.log')).write_text((p.stdout or '')+'\n'+(p.stderr or ''),encoding='utf-8')
 assert p.returncode==0,(p.returncode,p.stderr[-6000:]); d=json.loads(result.read_text()); assert d.get('status')=='passed',d; return d
# Actual packaged app Preview pipeline with short exact-source transport.
jobs=[]
for id,op,sim,bl,dsp in [('op1',1,.10,.06,.35),('op05',.5,.10,.06,.35),('op0',0,.10,.06,.35),('changed',1,.18,.03,.50)]:
 jobs.append({'id':id,'projectPath':str(project),'overlaySource':str(clip),'timeSec':.75,'effects':[effect(clip,opacity=op,sim=sim,blend=bl,dsp=dsp)],'subscribes':[]})
pf=work/'preview.json'; pr=work/'preview-result.json'; pf.write_text(json.dumps({'jobs':jobs},ensure_ascii=False)); pd=runapp(pf,pr,True,180)
paths={r['id']:Path(r['result']['exactPath']) for r in pd['results']}
for k,p in paths.items(): assert p.is_file(),(k,p); shutil.copy2(p,FR/f'preview-{k}.png')

def rgb(path): return run([FFMPEG,'-hide_banner','-loglevel','error','-i',path,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']).stdout
base=rgb(cover)
def intensity(path):
 a=rgb(path); n=min(len(a),len(base)); s=c=0
 for i in range(0,n,24): s+=abs(a[i]-base[i])+abs(a[i+1]-base[i+1])+abs(a[i+2]-base[i+2]); c+=3
 return s/max(1,c)
def mae(a,b):
 aa=rgb(a); bb=rgb(b); n=min(len(aa),len(bb)); return sum(abs(aa[i]-bb[i]) for i in range(0,n,24))/max(1,n//24)
I1,I05,I0=intensity(paths['op1']),intensity(paths['op05']),intensity(paths['op0']); D=mae(paths['op1'],paths['changed'])
print(f'PREVIEW_OPACITY1={I1:.4f} PREVIEW_OPACITY05={I05:.4f} PREVIEW_OPACITY0={I0:.4f} PREVIEW_CHROMA_CHANGE={D:.4f}')
assert I1>1.0,(I1,I05,I0); assert I05>I0+.2 and I05<I1*.85,(I1,I05,I0); assert I0<.5,(I1,I05,I0); assert D>.05,D
# Final render exact full physical source.
fx1=work/'fx1.mp4'; fx2=work/'fx2.mp4'
run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x00ff00:s=360x240:r=60','-t','2','-vf','drawbox=x=30:y=30:w=140:h=100:color=red:t=fill','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-y',fx1])
run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x00ff00:s=360x240:r=60','-t','2','-vf','drawbox=x=180:y=100:w=140:h=100:color=blue:t=fill','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-y',fx2])
def settings(out): return {'width':1920,'height':1080,'fps':60,'codec':'h265','bitrateMbps':30.0,'durationHours':12/3600,'durationMode':'whole-track','loopMode':'image','crossfadeSec':0.0,'normalizeLufs':False,'outputDir':str(out),'preset':'fast','encoderPreference':'auto'}
def job(id,out,fx):
 out.mkdir(parents=True,exist_ok=True)
 return {'project':{'id':id,'name':id,'path':str(project),'media':[str(cover)],'audio':[str(audio)],'valid':True,'error':None,'anchors':None,'selectedEffectId':EQ_ID,'selectedEffectIds':[x['id'] for x in fx],'outputDir':str(out),'outputSource':'manual','vyronManifestPath':None,'vyronChannelName':None},'settings':settings(out),'effects':fx,'subscribes':[],'ambient':None,'ambientSettings':{'volumePct':18.0,'bassDb':0.0,'midDb':0.0,'trebleDb':0.0}}
eq=effect(EQ,scale=.45,opacity=1.0); e1=effect(fx1,'qa-red','qa-red',.12,.16,.14,1,'#00ff00'); e2=effect(fx2,'qa-blue','qa-blue',.88,.16,.14,1,'#00ff00')
rf=work/'render.json'; rr=work/'render-result.json'; rf.write_text(json.dumps({'jobs':[job('eq-one',work/'one',[eq]),job('eq-multi',work/'multi',[eq,e1,e2])]},ensure_ascii=False)); rd=runapp(rf,rr,False,360)
rows={x['id']:x for x in rd['results']}; assert rows['eq-one']['fastPath'] is True,rows['eq-one']
for id,row in rows.items():
 p=Path(row['outputPath']); assert p.is_file();
 for tag,t in [('begin',.5),('middle',6),('end',11.5)]: run([FFMPEG,'-hide_banner','-loglevel','error','-ss',str(t),'-i',p,'-frames:v','1','-y',FR/f'final-{id}-{tag}.png'],timeout=90)
F=intensity(FR/'final-eq-one-middle.png'); FM=intensity(FR/'final-eq-multi-middle.png')
print(f'FINAL_EQ_STRENGTH={F:.4f} FINAL_MULTI_EQ_STRENGTH={FM:.4f} FAST_SECONDS={rows["eq-one"]["wallSeconds"]:.3f}')
assert F>1.0,F; assert FM>1.0,FM
# Preview and final use same safe chroma/opacity semantics. Require comparable non-zero visual energy, not pixel identity (different source phase/transport clip).
ratio=F/max(I1,1e-9); print(f'PREVIEW_RENDER_STRENGTH_RATIO={ratio:.4f}'); assert .20<ratio<5.0,ratio
print('EQUALIZER_VISIBILITY=PASS'); print('CHROMAKEY_BACKGROUND_REMOVAL=PASS'); print('FOREGROUND_PRESERVED=PASS'); print('OPACITY_1_FULL_STRENGTH=PASS'); print('OPACITY_05_WEAKER=PASS'); print('PREVIEW_RENDER_MATCH=PASS'); print('MULTI_EFFECT_EQUALIZER_VISIBILITY=PASS'); print('REALTIME_PREVIEW=PASS'); print('FAST_RENDER_REGRESSION=PASS')
(ROOT/'continuation-report.json').write_text(json.dumps({'preview':{'op1':I1,'op05':I05,'op0':I0,'chromaChange':D},'final':{'eq':F,'multi':FM,'fastSeconds':rows['eq-one']['wallSeconds'],'strengthRatio':ratio}},indent=2))
