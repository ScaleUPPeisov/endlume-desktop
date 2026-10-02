#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path

lib=Path.home()/"Library/Application Support/studio.endlume.desktop/library.json"
d=json.loads(lib.read_text())
sub=next(x for x in d.get("subscribes",[]) if isinstance(x,dict) and x.get("enabled") and Path(str(x.get("source",""))).is_file())
src=Path(str(sub["source"]))
ffmpeg=os.environ.get("FFMPEG") or "ffmpeg"
key=str(sub.get("keyColor","#00ff00")).lstrip("#")
sim=float(sub.get("similarity",0.1)); blend=float(sub.get("blend",0.06)); despill=float(sub.get("despill",0.35))
print(f"SUBSCRIBE_SOURCE={src}")
print(f"CURRENT_KEY={key} CURRENT_SIMILARITY={sim} CURRENT_BLEND={blend} CURRENT_DESPILL={despill}")

def sample(t,similarity,softness):
    vf=f"format=rgba,colorkey=0x{key}:{similarity}:{softness}"
    p=subprocess.run([ffmpeg,"-hide_banner","-loglevel","error","-ss",str(t),"-i",str(src),"-frames:v","1","-vf",vf,"-f","rawvideo","-pix_fmt","rgba","-"],
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=60)
    raw=p.stdout
    if not raw: return {"pixels":0,"a1":0,"a32":0,"a128":0,"a240":0,"mean":0}
    alpha=raw[3::4]; n=len(alpha)
    return {
      "pixels":n,
      "a1":sum(a>0 for a in alpha)/n,
      "a32":sum(a>=32 for a in alpha)/n,
      "a128":sum(a>=128 for a in alpha)/n,
      "a240":sum(a>=240 for a in alpha)/n,
      "mean":sum(alpha)/n,
    }

for t in (0.25,0.75,1.5,2.5,4.0):
    try:
        cur=sample(t,sim,blend)
        safe=sample(t,0.10,0.06)
        print("T=%.2f CURRENT=%s SAFE=%s"%(t,json.dumps(cur,separators=(",",":")),json.dumps(safe,separators=(",",":"))))
    except subprocess.CalledProcessError as e:
        print("T=%.2f ERROR=%s"%(t,e.stderr.decode("utf-8","replace")))
