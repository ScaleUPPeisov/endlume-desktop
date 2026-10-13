#!/usr/bin/env python3
import json, math, subprocess, sys
from collections import Counter
from pathlib import Path
F=Path(sys.argv[1]); P=Path(sys.argv[2]); ROOT=Path(sys.argv[3]); OUT=ROOT/'frames'; OUT.mkdir(parents=True,exist_ok=True)

def run(a,ok=True,t=45):
 p=subprocess.run([str(x) for x in a],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=t)
 if ok and p.returncode: raise RuntimeError(p.stderr.decode(errors='replace')[-4000:])
 return p

def meta(path):
 try:
  d=json.loads(run([P,'-v','error','-select_streams','v:0','-show_entries','stream=width,height,duration:format=duration','-of','json',path],t=15).stdout); s=(d.get('streams') or [None])[0]
  if not s:return None
  w=int(s.get('width') or 0);h=int(s.get('height') or 0);dur=float(s.get('duration') or d.get('format',{}).get('duration') or 2)
  return (w,h,dur if math.isfinite(dur) and dur>0 else 2) if w>1 and h>1 else None
 except:return None

def small(path,t):
 p=run([F,'-hide_banner','-loglevel','error','-ss',f'{t:.4f}','-i',path,'-vf','scale=160:90:flags=area','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],False,20)
 return p.stdout if p.returncode==0 and len(p.stdout)>=160*90*3 else b''

def score(path):
 m=meta(path)
 if not m:return None
 w,h,d=m; raws=[x for x in (small(path,min(.12,d*.1)),small(path,d*.5),small(path,max(0,d-.12))) if x]
 if not raws:return None
 green=total=0; hist=Counter()
 for raw in raws:
  for i in range(0,len(raw)-2,3):
   r,g,b=raw[i:i+3];total+=1
   if g>=70 and g>=r+24 and g>=b+18 and g>=max(r,b)*1.22:
    green+=1;hist[(r//8,g//8,b//8)]+=1
 frac=green/max(1,total); fg=1-frac
 key='#00ff00'
 if hist:
  q=hist.most_common(1)[0][0]; vals=[]
  for raw in raws:
   for i in range(0,len(raw)-2,3):
    r,g,b=raw[i:i+3]
    if (r//8,g//8,b//8)==q: vals.append((r,g,b))
  if vals:
   r=round(sum(x[0] for x in vals)/len(vals));g=round(sum(x[1] for x in vals)/len(vals));b=round(sum(x[2] for x in vals)/len(vals));key=f'#{r:02x}{g:02x}{b:02x}'
 return {'path':str(path),'w':w,'h':h,'duration':d,'greenFraction':frac,'foregroundFraction':fg,'key':key}

files=[]
for base in [Path.home()/'Library/Application Support',Path.home()/'Library/Containers']:
 if base.exists():
  files += [p for p in base.rglob('library-assets/effects/*') if p.is_file()]
print('MANAGED_EFFECT_FILES='+str(len(files)))
scored=[s for p in files if (s:=score(p)) and s['greenFraction']>.25 and .002<s['foregroundFraction']<.70]
scored.sort(key=lambda x:x['greenFraction'],reverse=True)
(ROOT/'managed-candidates.json').write_text(json.dumps(scored,ensure_ascii=False,indent=2))
for i,s in enumerate(scored): print(f'MANAGED_CANDIDATE_{i+1}='+json.dumps(s,ensure_ascii=False,separators=(',',':')))
if not scored: raise AssertionError('NO_GREENSCREEN_MANAGED_EFFECT')
S=scored[0]; source=Path(S['path']);W=S['w'];H=S['h'];D=S['duration'];key=S['key'];rawkey=key[1:];K='0x'+rawkey;kr,kg,kb=[int(rawkey[i:i+2],16) for i in (0,2,4)]
print('SELECTED_SOURCE='+json.dumps(S,ensure_ascii=False,separators=(',',':')))
CASES={'owner_raw_max':(.60,.35,1.),'candidate_current':(.18,.03,1.),'safe_010_006_035':(.10,.06,.35),'safe_014_006_035':(.14,.06,.35),'safe_018_003_020':(.18,.03,.20),'safe_018_003_035':(.18,.03,.35),'safe_018_003_050':(.18,.03,.50),'safe_018_006_035':(.18,.06,.35)}
TIMES={'begin':max(0,min(D-.02,.12)),'middle':D*.5,'end':max(0,D-.12)}
def raw(t):return run([F,'-hide_banner','-loglevel','error','-ss',f'{t:.4f}','-i',source,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],t=40).stdout
def keyed(t,sim,blend,dsp):return run([F,'-hide_banner','-loglevel','error','-ss',f'{t:.4f}','-i',source,'-vf',f'format=rgba,colorkey={K}:{sim}:{blend},despill=type=green:mix={dsp}:expand=.20,format=rgba','-frames:v','1','-f','rawvideo','-pix_fmt','rgba','-'],t=40).stdout
def metrics(a,b):
 n=min(len(a)//3,len(b)//4);fg=bg=0;fa=ba=re=oe=spill=0.
 for i in range(n):
  r,g,bb=a[3*i:3*i+3]; rr,gg,bbb,al=b[4*i:4*i+4]; dist=math.sqrt((r-kr)**2+(g-kg)**2+(bb-kb)**2)/441.673
  if dist>=.20: fg+=1;fa+=al/255;re+=(r+g+bb)/765;oe+=(rr+gg+bbb)/765;spill+=max(gg-max(rr,bbb),0)/255
  elif dist<=.055:bg+=1;ba+=al/255
 return {'foregroundAlpha':fa/max(1,fg),'backgroundRemoved':1-ba/max(1,bg),'energyRatio':(oe/max(1,fg))/(re/max(1,fg)+1e-12),'greenExcess':spill/max(1,fg),'fgPixels':fg,'bgPixels':bg}
def image(t,label,name,sim=.18,blend=.03,dsp=.35,op=1):
 dst=OUT/f'{label}-{name}.png'; vf=f'format=rgba,colorkey={K}:{sim}:{blend},despill=type=green:mix={dsp}:expand=.20,colorchannelmixer=aa={op}'
 run([F,'-hide_banner','-loglevel','error','-ss',f'{t:.4f}','-i',source,'-f','lavfi','-i',f'color=c=0x202020:s={W}x{H}:r=1','-filter_complex',f'[0:v]{vf}[fx];[1:v][fx]overlay=0:0:format=auto','-frames:v','1','-y',dst],t=40)
report={'candidate':'c5534ce47123777b698117a46473238381e37729','source':S,'frames':{}}
for label,t in TIMES.items():
 a=raw(t); row={}
 for name,v in CASES.items():row[name]=metrics(a,keyed(t,*v))
 report['frames'][label]=row
 for name,v in [('current',(.18,.03,1.)),('safe020',(.18,.03,.20)),('safe035',(.18,.03,.35)),('safe050',(.18,.03,.50)),('default1006035',(.10,.06,.35))]:image(t,label,name,*v)
 image(t,label,'opacity050',.18,.03,.35,.5);image(t,label,'opacity000',.18,.03,.35,0)
agg={}
for name in CASES:
 vals=[report['frames'][x][name] for x in TIMES];agg[name]={k:sum(v[k] for v in vals)/len(vals) for k in ('foregroundAlpha','backgroundRemoved','energyRatio','greenExcess')}
report['aggregate']=agg;(ROOT/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
for n,m in agg.items():print(n.upper()+'='+json.dumps(m,separators=(',',':')))
print('PHYSICAL_EQUALIZER_PROBE=PASS')
