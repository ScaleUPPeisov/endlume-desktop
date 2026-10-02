#!/usr/bin/env python3
import json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

APP=Path(sys.argv[1]).resolve()
FFMPEG=Path(sys.argv[2]).resolve()
FFPROBE=Path(sys.argv[3]).resolve()
REPORT=Path(sys.argv[4]).resolve()
VOL=Path("/Volumes/TOSHIBA EXT")
OUT=VOL/"ВАЙРОН"/"Render"/"Brewroom Jazz"
assert APP.is_file(),APP
assert FFMPEG.is_file() and FFPROBE.is_file(),(FFMPEG,FFPROBE)
assert VOL.is_dir() and OUT.is_dir(),OUT
REPORT.parent.mkdir(parents=True,exist_ok=True)

IMAGE={".jpg",".jpeg",".png",".webp",".bmp",".tif",".tiff",".heic",".avif"}
VIDEO={".mp4",".mov",".m4v",".mkv",".webm",".avi",".wmv",".flv",".ts",".mts",".m2ts",".mpg",".mpeg",".vob",".3gp"}
AUDIO={".mp3",".wav",".m4a",".aac",".flac",".ogg",".opus",".aiff",".aif",".alac"}

def run(args,check=True,timeout=180,env=None):
    return subprocess.run([str(x) for x in args],check=check,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,env=env)

def probe(path):
    return json.loads(run([FFPROBE,"-v","error","-show_entries","stream=codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels,bit_rate:format=duration,size","-of","json",path]).stdout)

def frame(path,pos=1.0):
    p=subprocess.run([str(FFMPEG),"-hide_banner","-loglevel","error","-ss",str(pos),"-i",str(path),"-map","0:v:0","-frames:v","1","-f","rawvideo","-pix_fmt","rgb24","-"],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
    assert len(p.stdout)==1920*1080*3,(path,len(p.stdout))
    return p.stdout

def diff_stats(a,b,step_pixels=4,threshold=8):
    assert len(a)==len(b)
    changed=0;total=0;sumd=0;maxd=0
    stride=3*step_pixels
    for i in range(0,len(a)-2,stride):
        d=max(abs(a[i]-b[i]),abs(a[i+1]-b[i+1]),abs(a[i+2]-b[i+2]))
        total+=1;sumd+=d;maxd=max(maxd,d)
        if d>=threshold:changed+=1
    return {"sampled":total,"changed":changed,"ratio":changed/max(1,total),"meanMaxDiff":sumd/max(1,total),"maxDiff":maxd}

def resolve_project():
    roots=[]
    log_dir=OUT/"logs"
    if log_dir.is_dir():
        for log in sorted(log_dir.glob("*error.txt"),key=lambda p:p.stat().st_mtime,reverse=True):
            try:text=log.read_text(errors="replace")
            except Exception:continue
            m=re.search(r"^Path:\s*(.+)$",text,re.M)
            if m:
                p=Path(m.group(1).strip())
                if p.is_dir():roots.append(p);break
    if not roots:
        data_root=Path.home()/"Library/Application Support/studio.endlume.desktop"
        for state_name in ("queue.json","recovery.json"):
            p=data_root/state_name
            if not p.is_file():continue
            try:d=json.load(open(p))
            except Exception:continue
            jobs=[]
            if isinstance(d,dict):
                if isinstance(d.get("active"),dict):jobs.append(d["active"])
                jobs.extend(x for x in (d.get("pending") or []) if isinstance(x,dict))
            for job in jobs:
                proj=job.get("project") or {}
                hay=" ".join(map(str,[proj.get("name",""),proj.get("path","")])).lower()
                if "brewroom jazz" in hay or "новая папка" in hay:
                    q=Path(str(proj.get("path","")))
                    if q.is_dir():roots.append(q);break
            if roots:break
    if not roots:
        base=VOL/"ВАЙРОН"
        for p in base.rglob("*"):
            if not p.is_dir():continue
            try:files=[x for x in p.iterdir() if x.is_file() and not x.name.startswith(".")]
            except Exception:continue
            if any(x.suffix.lower() in IMAGE|VIDEO for x in files) and any(x.suffix.lower() in AUDIO for x in files) and ("brewroom" in str(p).lower() or p.name.lower()=="новая папка"):
                roots.append(p);break
    assert roots,"BREWROOM_JAZZ_REAL_PROJECT_NOT_FOUND"
    candidates=[]
    for base in roots[:2]:
        dirs=[base]+[p for p in base.rglob("*") if p.is_dir()]
        for d in dirs:
            try:files=[p for p in d.iterdir() if p.is_file() and not p.name.startswith(".") and not p.name.startswith("._")]
            except Exception:continue
            media=sorted([p for p in files if p.suffix.lower() in IMAGE|VIDEO],key=lambda x:x.name.lower())
            songs=sorted([p for p in files if p.suffix.lower() in AUDIO],key=lambda x:x.name.lower())
            if media and len(songs)>=8:candidates.append((len(songs),-len(str(d)),d,media,songs))
    assert candidates,"BREWROOM_JAZZ_8_TRACK_FIXTURE_NOT_FOUND"
    _,_,project,media,songs=max(candidates)
    return project,media,songs[:15]

def load_library():
    for base in [Path.home()/"Library/Application Support",Path.home()/"Library/Containers"]:
        if not base.exists():continue
        for p in base.rglob("library.json"):
            try:
                if p.stat().st_size>10_000_000:continue
                d=json.load(open(p))
            except Exception:continue
            fx=[x for x in d.get("effects",[]) if isinstance(x,dict) and Path(str(x.get("source",""))).is_file()]
            if any(x.get("id")=="825dd7a4-f0cf-4032-a3c9-64290cb5756d" or "эквалайзер круглый" in str(x.get("name","")).lower() for x in fx):
                return p,d
    raise AssertionError("ENDLUME_LIBRARY_WITH_ROUND_EQUALIZER_NOT_FOUND")

project,media,songs=resolve_project()
lib_path,lib=load_library()
fx=[dict(x) for x in lib.get("effects",[]) if isinstance(x,dict) and Path(str(x.get("source",""))).is_file()]
eq=next(x for x in fx if x.get("id")=="825dd7a4-f0cf-4032-a3c9-64290cb5756d" or "эквалайзер круглый" in str(x.get("name","")).lower())
ordinary=[x for x in fx if x.get("id")!=eq.get("id")]
film=next((x for x in ordinary if any(t in str(x.get("name","")).lower() for t in ("80","плен","пыль","царап"))),ordinary[0] if ordinary else None)
assert film,"80S_EFFECT_NOT_FOUND"
third=next((x for x in ordinary if x.get("id")!=film.get("id")),None)
subs=[dict(x) for x in lib.get("subscribes",[]) if isinstance(x,dict) and Path(str(x.get("source",""))).is_file()]
assert subs,"REAL_SUBSCRIBE_NOT_FOUND"
sub=subs[0]

tmp_root=Path(tempfile.mkdtemp(prefix="endlume1011-post-preview-"))
if third is None:
    # The user's current library may only contain the 80s Film + Round Equalizer.
    # Add one QA-only ordinary chromakey layer so the compositor is still tested
    # with the required third Effect without mutating the persisted library.
    src=tmp_root/"qa-third-effect.mp4"
    run([FFMPEG,"-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=0x00ff00:size=640x360:rate=30","-t","2","-vf","drawbox=x=120:y=80:w=400:h=180:color=red@1:t=fill,drawbox=x=200:y=130:w=240:h=80:color=white@1:t=fill","-c:v","libx264","-preset","ultrafast","-pix_fmt","yuv420p","-y",src],timeout=60)
    third={"id":"e1011-qa-third","name":"QA Third Ordinary Effect","source":str(src),"enabled":True,"mode":"chromakey","keyColor":"#00ff00","similarity":0.10,"blend":0.06,"despill":0.35,"lumaThreshold":0.03,"lumaTolerance":0.08,"saturation":1.0,"x":0.72,"y":0.32,"scale":0.28,"fullscreen":False,"previewFrameTime":0.0,"startSec":0.0,"endSec":None,"cacheKey":None,"cacheReady":False,"usageMode":"always","intervalSec":240.0,"usageDurationSec":30.0,"target":None,"offsetX":None,"offsetY":None,"opacity":1.0}

def always(e):
    x=dict(e);x.update({"enabled":True,"usageMode":"always","startSec":0.0,"endSec":None})
    return x
film=always(film);eq=always(eq);third=always(third)
sub.update({"enabled":True,"usageMode":"interval","intervalSec":240.0,"repeatEverySec":240.0,"firstAppearance":"immediate","customFirstAtSec":0.0,"firstAtSec":0.0,"secondAtSec":240.0,"showDurationSec":8.0,"usageDurationSec":8.0})

settings={"width":1920,"height":1080,"fps":60,"codec":"h265","bitrateMbps":8.0,"durationHours":2.0,"durationMode":"whole-track","loopMode":"image","crossfadeSec":0.0,"normalizeLufs":False,"outputDir":str(OUT),"preset":"fast","encoderPreference":"auto"}
common_project={"path":str(project),"media":[str(media[0])],"audio":[str(x) for x in songs],"valid":True,"error":None,"anchors":{}}

def perf_job(pid,name):
    return {"project":dict(common_project,id=pid,name=name),"settings":settings,"effects":[film,eq,third],"subscribes":[sub],"ambient":None}

jobs=[perf_job("e1011-perf-cold","ENDLUME 10.0.11 PERF COLD"),perf_job("e1011-perf-warm","ENDLUME 10.0.11 PERF WARM")]
fixture=tmp_root/"perf-jobs.json";result=tmp_root/"perf-result.json"
fixture.write_text(json.dumps({"jobs":jobs},ensure_ascii=False,indent=2))
env=os.environ.copy();env.update({"ENDLUME_E2E_RENDER_JOB":str(fixture),"ENDLUME_E2E_RESULT":str(result),"RUST_BACKTRACE":"1"})
rp=run([APP],check=False,timeout=240,env=env)
(tmp_root/"perf.stderr").write_text(rp.stderr);(tmp_root/"perf.stdout").write_text(rp.stdout)
print("PERF_APP_EXIT="+str(rp.returncode))
for line in rp.stderr.splitlines():
    if "ENDLUME_DIAG " not in line:continue
    try:d=json.loads(line.split("ENDLUME_DIAG ",1)[1].strip())
    except Exception:continue
    if d.get("projectId") in ("e1011-perf-cold","e1011-perf-warm") or d.get("id") in ("e1011-perf-cold","e1011-perf-warm"):
        print("PERF_DIAG="+json.dumps(d,ensure_ascii=False,sort_keys=True))
assert rp.returncode==0,(rp.returncode,rp.stderr[-12000:])
raw=json.loads(result.read_text());assert raw.get("status")=="passed",raw
rows={x["id"]:x for x in raw["results"]}
assert set(rows)=={"e1011-perf-cold","e1011-perf-warm"},rows
for pid,row in rows.items():
    p=Path(row["outputPath"]);assert p.is_file(),p
    m=probe(p);v=next(x for x in m["streams"] if x.get("codec_type")=="video");a=next(x for x in m["streams"] if x.get("codec_type")=="audio")
    mib=p.stat().st_size/1048576
    print(f"PERF_ROW id={pid} wall={float(row['wallSeconds']):.6f} mib={mib:.3f} encoder={row.get('encoder')} fastPath={row.get('fastPath')}")
    assert v["codec_name"]=="hevc" and v["width"]==1920 and v["height"]==1080 and v["avg_frame_rate"]=="60/1",(pid,v)
    assert a["codec_name"]=="aac" and int(a["sample_rate"])==48000 and int(a["channels"])==2,(pid,a)
    assert 400<=mib<=600,(pid,mib)
cold=float(rows["e1011-perf-cold"]["wallSeconds"]);warm=float(rows["e1011-perf-warm"]["wallSeconds"])
print(f"PERF_COLD_SECONDS={cold:.6f}")
print(f"PERF_WARM_SECONDS={warm:.6f}")
print(f"PERF_DELTA_SECONDS={cold-warm:.6f}")
if cold<=20.0:
    print("FINAL_RENDER_PERFORMANCE=GREEN")
else:
    print("FINAL_RENDER_PERFORMANCE=RED")
    raise AssertionError(("PERF_COLD_OVER_20",cold,warm,cold-warm))
for row in rows.values():
    try:Path(row["outputPath"]).unlink()
    except Exception:pass
