#!/usr/bin/env python3
import json, os, shutil, subprocess, sys
from pathlib import Path

OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path('857-subscribe-preset.json').resolve()
ROOTS=[Path('/Volumes/TOSHIBA EXT'),Path.home()/'Library'/'Application Support',Path.home()/'.endlume-ci-fixtures']


def resolve(raw,side):
    if not isinstance(raw,str) or not raw.strip(): return None
    p=Path(os.path.expanduser(raw))
    if p.is_file(): return p.resolve()
    if not p.is_absolute():
        for base in [side.parent,*list(side.parents)[:7]]:
            q=base/p
            if q.is_file(): return q.resolve()
    return None


def candidates():
    seen=set()
    for root in ROOTS:
        if not root.exists(): continue
        try:
            r=subprocess.run(['/usr/bin/find',str(root),'-type','f','-name','*project.json','-print'],capture_output=True,text=True,timeout=45,check=False)
        except subprocess.TimeoutExpired:
            continue
        for line in r.stdout.splitlines():
            p=Path(line)
            if str(p) not in seen:
                seen.add(str(p)); yield p
    # persisted JSON can contain a QueueJob snapshot with subscribes
    app=Path.home()/'Library'/'Application Support'
    if app.exists():
        try:
            r=subprocess.run(['/usr/bin/find',str(app),'-maxdepth','7','-type','f','(','-name','library.json','-o','-name','queue.json','-o','-name','recovery.json','-o','-name','session.json',')','-print'],capture_output=True,text=True,timeout=30,check=False)
            for line in r.stdout.splitlines(): yield Path(line)
        except subprocess.TimeoutExpired: pass


def walk(obj,origin):
    if isinstance(obj,dict):
        subs=obj.get('subscribes')
        if isinstance(subs,list):
            for sub in subs:
                if not isinstance(sub,dict): continue
                src=resolve(sub.get('source'),origin)
                if not src: continue
                yield {
                    'origin':str(origin),'source':str(src),'enabled':bool(sub.get('enabled')),
                    'id':sub.get('id'),'name':sub.get('name'),'mode':sub.get('mode'),
                    'keyColor':sub.get('keyColor'),'similarity':sub.get('similarity'),'blend':sub.get('blend'),
                    'despill':sub.get('despill'),'lumaThreshold':sub.get('lumaThreshold'),'lumaTolerance':sub.get('lumaTolerance'),
                    'saturation':sub.get('saturation'),'x':sub.get('x'),'y':sub.get('y'),'scale':sub.get('scale'),
                    'fullscreen':sub.get('fullscreen'),'previewFrameTime':sub.get('previewFrameTime'),
                    'startSec':sub.get('startSec'),'endSec':sub.get('endSec'),
                    'firstAtSec':sub.get('firstAtSec'),'secondAtSec':sub.get('secondAtSec'),'repeatEverySec':sub.get('repeatEverySec')
                }
        for v in obj.values(): yield from walk(v,origin)
    elif isinstance(obj,list):
        for v in obj: yield from walk(v,origin)

found=[]
for p in candidates():
    try: obj=json.loads(p.read_text(errors='replace'))
    except Exception: continue
    found.extend(walk(obj,p))

# Prefer a currently enabled, periodic preset that runtime's zero-copy planner supports.
def score(x):
    valid_sched=all(isinstance(x.get(k),(int,float)) for k in ['firstAtSec','secondAtSec','repeatEverySec']) and float(x.get('repeatEverySec') or 0)>=60
    non_screen=str(x.get('mode') or '') not in ('screen','screen-cache','strict-screen-cache')
    return (bool(x.get('enabled')),valid_sched,non_screen,-len(str(x.get('origin') or '')))
found.sort(key=score,reverse=True)
if not found:
    print('[subscribe] NO REAL SUBSCRIBE PRESET WITH EXISTING SOURCE FOUND',flush=True)
    raise SystemExit(2)
sel=found[0]
stage=Path.home()/'.endlume-ci-fixtures'/'subscribe-857'; stage.mkdir(parents=True,exist_ok=True)
src=Path(sel['source']); dst=stage/('subscribe'+src.suffix.lower())
if not dst.exists() or dst.stat().st_size!=src.stat().st_size: shutil.copy2(src,dst)
sel['source']=str(dst.resolve())
OUT.write_text(json.dumps(sel,ensure_ascii=False,indent=2))
print('[subscribe] FOUND',json.dumps(sel,ensure_ascii=False),flush=True)
