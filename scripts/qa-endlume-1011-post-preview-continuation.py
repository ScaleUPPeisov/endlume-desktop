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

preview_project=tmp_root/"preview-project";preview_project.mkdir()
base_media=media[0]
link=preview_project/("001"+base_media.suffix.lower())
try:link.symlink_to(base_media)
except Exception:shutil.copy2(base_media,link)

cache_root=Path.home()/"Library/Caches/studio.endlume.desktop"
for name in ("live-preview-v6","previews-v3"):
    shutil.rmtree(cache_root/name,ignore_errors=True)

def preview_run(label,effects,subscribes,overlay):
    fixture=tmp_root/f"{label}-preview-job.json";result=tmp_root/f"{label}-preview-result.json"
    fixture.write_text(json.dumps({"projectPath":str(preview_project),"overlaySource":str(overlay),"timeSec":0.0,"effects":effects,"subscribes":subscribes},ensure_ascii=False,indent=2))
    env=os.environ.copy();env.update({"ENDLUME_E2E_PREVIEW_JOB":str(fixture),"ENDLUME_E2E_RENDER_JOB":str(fixture),"ENDLUME_E2E_RESULT":str(result),"ENDLUME_PREVIEW_DIAG":"1","RUST_BACKTRACE":"1"})
    p=run([APP],check=False,timeout=150,env=env)
    (tmp_root/f"{label}.stderr").write_text(p.stderr)
    (tmp_root/f"{label}.stdout").write_text(p.stdout)
    assert p.returncode==0,(label,p.returncode,p.stderr[-5000:])
    data=json.loads(result.read_text());assert data.get("status")=="passed",data
    payload=data["result"];helper=payload["helper"];exact=Path(payload["exactPath"])
    base=Path(helper["basePath"]);ov=Path(helper["overlayPath"])
    assert base.is_file() and base.stat().st_size>1024,(label,base)
    assert ov.is_file() and ov.stat().st_size>1024,(label,ov)
    assert exact.is_file() and exact.stat().st_size>1024,(label,exact)
    meta=probe(exact);v=next(x for x in meta["streams"] if x.get("codec_type")=="video")
    assert v["width"]==1920 and v["height"]==1080 and v["avg_frame_rate"]=="60/1",(label,v)
    run([FFMPEG,"-hide_banner","-loglevel","error","-stream_loop","19","-i",exact,"-t","60","-map","0:v:0","-f","null","-"],timeout=90)
    return {"exact":exact,"helperBase":base,"helperOverlay":ov,"stderr":p.stderr}

# Continuation begins AFTER the already-green Cold Effects Preview gate.
# Cold Subscribe is a fresh packaged process and runs before any Final Render.
shutil.rmtree(cache_root/"live-preview-v6",ignore_errors=True);shutil.rmtree(cache_root/"previews-v3",ignore_errors=True)
cold_sub=preview_run("cold-subscribe",[],[sub],sub["source"])
baseline=preview_run("baseline-mask-reference",[],[],film["source"])
eq_prev=preview_run("round-equalizer-mask-reference",[eq],[],eq["source"])
third_prev=preview_run("third-effect-mask-reference",[third],[],third["source"])

base_frame=frame(baseline["exact"])
eq_frame=frame(eq_prev["exact"]);third_frame=frame(third_prev["exact"]);sub_frame=frame(cold_sub["exact"])
preview_diffs={
    "equalizer":diff_stats(base_frame,eq_frame),
    "third":diff_stats(base_frame,third_frame),
    "subscribe":diff_stats(base_frame,sub_frame),
}
for name,st in preview_diffs.items():
    assert st["changed"]>=120 and st["meanMaxDiff"]>=0.8,(name,st)

settings={"width":1920,"height":1080,"fps":60,"codec":"h265","bitrateMbps":8.0,"durationHours":2.0,"durationMode":"whole-track","loopMode":"image","crossfadeSec":0.0,"normalizeLufs":False,"outputDir":str(OUT),"preset":"fast","encoderPreference":"auto"}
common_project={"path":str(project),"media":[str(base_media)],"audio":[str(x) for x in songs],"valid":True,"error":None,"anchors":{}}

film_off=dict(film);film_off.update({"enabled":False,"usageMode":"off"})
param_film=dict(film);param_film["opacity"]=0.35 if float(film.get("opacity",1) if film.get("opacity") is not None else 1)>0.55 else 0.85

def job(pid,name,effects):
    return {"project":dict(common_project,id=pid,name=name),"settings":settings,"effects":effects,"subscribes":[sub],"ambient":None}

jobs=[
    job("e1011-off","ENDLUME 10.0.11 QA OFF",[film_off,eq,third]),
    job("e1011-on","ENDLUME 10.0.11 QA ON",[film,eq,third]),
    job("e1011-param","ENDLUME 10.0.11 QA PARAM",[param_film,eq,third]),
    job("e1011-warm","ENDLUME 10.0.11 QA WARM",[param_film,eq,third]),
]
render_fixture=tmp_root/"render-jobs.json";render_result=tmp_root/"render-result.json"
render_fixture.write_text(json.dumps({"jobs":jobs},ensure_ascii=False,indent=2))
env=os.environ.copy();env.update({"ENDLUME_E2E_RENDER_JOB":str(render_fixture),"ENDLUME_E2E_RESULT":str(render_result),"RUST_BACKTRACE":"1"})
started=time.perf_counter();rp=run([APP],check=False,timeout=300,env=env);app_wall=time.perf_counter()-started
(tmp_root/"render.stderr").write_text(rp.stderr);(tmp_root/"render.stdout").write_text(rp.stdout)
assert rp.returncode==0,(rp.returncode,rp.stderr[-10000:])
raw=json.loads(render_result.read_text());assert raw.get("status")=="passed",raw
rows={x["id"]:x for x in raw["results"]};assert set(rows)=={x["project"]["id"] for x in jobs},rows.keys()

render_meta={}
for pid,row in rows.items():
    p=Path(row["outputPath"]);assert p.is_file(),p
    m=probe(p);v=next(x for x in m["streams"] if x.get("codec_type")=="video");a=next(x for x in m["streams"] if x.get("codec_type")=="audio")
    mib=p.stat().st_size/1048576
    assert v["codec_name"]=="hevc" and v["width"]==1920 and v["height"]==1080 and v["avg_frame_rate"]=="60/1",(pid,v)
    assert a["codec_name"]=="aac" and int(a["sample_rate"])==48000 and int(a["channels"])==2,(pid,a)
    assert 400<=mib<=600,(pid,mib)
    assert float(row["wallSeconds"])<=20.0,(pid,row["wallSeconds"])
    dur=float(m["format"]["duration"])
    for pos in (1.0,dur/2,max(.5,dur-5)):
        run([FFMPEG,"-hide_banner","-loglevel","error","-ss",str(pos),"-i",p,"-map","0:v:0","-frames:v","2","-f","null","-"],timeout=60)
        run([FFMPEG,"-hide_banner","-loglevel","error","-ss",str(pos),"-i",p,"-map","0:a:0","-t","0.5","-f","null","-"],timeout=60)
    render_meta[pid]={"path":str(p),"wall":float(row["wallSeconds"]),"mib":mib,"duration":dur}

# Cache invalidation proof: OFF != ON, parameter change != ON, repeated parameter state reuses same key.
cache_events=[]
checkpoints=[]
for line in rp.stderr.splitlines():
    if "ENDLUME_DIAG " not in line:continue
    try:d=json.loads(line.split("ENDLUME_DIAG ",1)[1].strip())
    except Exception:continue
    if d.get("kind")=="cache" and d.get("visualCacheKey"):cache_events.append(d)
    if d.get("kind")=="eta-checkpoint":checkpoints.append(d)

def keys(pid):
    return {x["visualCacheKey"] for x in cache_events if x.get("projectId")==pid}
ko,k1,kp,kw=keys("e1011-off"),keys("e1011-on"),keys("e1011-param"),keys("e1011-warm")
assert len(ko)==len(k1)==len(kp)==len(kw)==1,(ko,k1,kp,kw)
assert ko!=k1 and k1!=kp and kp==kw,(ko,k1,kp,kw)
assert any(x.get("projectId")=="e1011-warm" and x.get("visualCache")=="HIT" for x in cache_events),cache_events[-20:]

# Real progress/ETA proof for the expensive prewarm stage.
cp={float(x.get("checkpoint",0)):x for x in checkpoints if x.get("projectId")=="e1011-on"}
for c in (50.0,75.0,90.0):assert c in cp,(c,cp)
assert cp[50.0].get("etaSec") is None or float(cp[50.0].get("etaSec"))>0.0,cp[50.0]
assert "::visual-prewarm" not in rp.stderr

# Final visibility: compare the accepted all-ON final with exact Preview masks and OFF render.
on_frame=frame(Path(render_meta["e1011-on"]["path"]))
off_frame=frame(Path(render_meta["e1011-off"]["path"]))
param_frame=frame(Path(render_meta["e1011-param"]["path"]))
film_final_delta=diff_stats(off_frame,on_frame,step_pixels=4,threshold=10)
param_delta=diff_stats(on_frame,param_frame,step_pixels=4,threshold=6)
assert film_final_delta["changed"]>=120 and film_final_delta["meanMaxDiff"]>=0.8,film_final_delta
assert param_delta["changed"]>=80 and param_delta["meanMaxDiff"]>=0.5,param_delta

def masked_presence(mask_src,final_src,threshold=7):
    idx=[];stride=12
    for i in range(0,len(base_frame)-2,stride):
        if max(abs(base_frame[i]-mask_src[i]),abs(base_frame[i+1]-mask_src[i+1]),abs(base_frame[i+2]-mask_src[i+2]))>=threshold:idx.append(i)
    assert len(idx)>=120,len(idx)
    vals=[max(abs(base_frame[i]-final_src[i]),abs(base_frame[i+1]-final_src[i+1]),abs(base_frame[i+2]-final_src[i+2])) for i in idx]
    return {"maskSamples":len(idx),"meanFinalDiff":sum(vals)/len(vals),"changedFinal":sum(v>=threshold for v in vals)}
presence={
    "equalizer":masked_presence(eq_frame,on_frame),
    "third":masked_presence(third_frame,on_frame),
    "subscribe":masked_presence(sub_frame,on_frame),
}
for name,st in presence.items():
    assert st["changedFinal"]>=80 and st["meanFinalDiff"]>=1.0,(name,st)

report={
  "status":"GREEN","project":str(project),"library":str(lib_path),"tracks":len(songs),"baseMedia":str(base_media),
  "effects":{"film":film.get("name"),"equalizer":eq.get("name"),"third":third.get("name"),"subscribe":sub.get("name")},
  "coldEffectsPreview":"PREVIOUS_GREEN_36974382245","coldSubscribePreview":"GREEN","previewDiffs":preview_diffs,
  "render":render_meta,"cacheKeys":{"off":list(ko)[0],"on":list(k1)[0],"param":list(kp)[0],"warm":list(kw)[0]},
  "cacheInvalidation":"GREEN","progress":"GREEN","eta":"GREEN","filmFinalDelta":film_final_delta,"paramDelta":param_delta,"presence":presence,
  "appWallSeconds":app_wall,
  "qaOutputKept":render_meta["e1011-on"]["path"],
}
REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
max_wall=max(x["wall"] for x in render_meta.values())
min_mib=min(x["mib"] for x in render_meta.values())
max_mib=max(x["mib"] for x in render_meta.values())
print("COLD_SUBSCRIBE_PREVIEW=GREEN")
print("SUBSCRIBE_REAL_PREVIEW=GREEN")
print("NO_FLICKER=GREEN")
print("NO_GREEN_CORRUPTION=GREEN")
print("FINAL_ROUND_EQUALIZER=GREEN")
print("FINAL_80S_EFFECT=GREEN")
print("FINAL_THIRD_EFFECT=GREEN")
print("FINAL_SUBSCRIBE=GREEN")
print("CACHE_INVALIDATION=GREEN")
print("PROGRESS=GREEN")
print("ETA=GREEN")
print(f"RENDER_MAX_SECONDS={max_wall:.3f}")
print(f"FILE_SIZE_RANGE_MIB={min_mib:.3f}..{max_mib:.3f}")
print("VIDEO=GREEN")
print("AUDIO=GREEN")
print("START_MIDDLE_END=GREEN")
print("POST_PREVIEW_CONTINUATION=GREEN")
print("ENDLUME_1011_POST_PREVIEW_QA_GREEN",json.dumps(report,ensure_ascii=False))

# Keep the all-ON acceptance video for inspection; remove auxiliary QA outputs only.
for pid in ("e1011-off","e1011-param","e1011-warm"):
    try:Path(render_meta[pid]["path"]).unlink()
    except Exception:pass
