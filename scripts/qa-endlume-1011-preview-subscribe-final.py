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

def poster_frame(path):
    p=subprocess.run([str(FFMPEG),"-hide_banner","-loglevel","error","-i",str(path),"-vf","scale=1920:1080:flags=neighbor","-frames:v","1","-f","rawvideo","-pix_fmt","rgb24","-"],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
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

tmp_root=Path(tempfile.mkdtemp(prefix="endlume1011-qa-"))
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

# Use the REAL persisted Subscribe state. Do not rewrite chroma/schedule for this acceptance.
assert sub.get("enabled") is True,sub
assert str(sub.get("usageMode"))=="interval",sub
assert str(sub.get("firstAppearance"))=="immediate",sub
assert abs(float(sub.get("intervalSec",sub.get("repeatEverySec",0)))-240.0)<0.01,sub
assert 2.0<=float(sub.get("showDurationSec",0))<=20.0,sub

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
    (tmp_root/f"{label}.backend.stderr").write_text(p.stderr)
    (tmp_root/f"{label}.backend.stdout").write_text(p.stdout)
    assert p.returncode==0,(label,p.returncode,p.stderr[-8000:])
    data=json.loads(result.read_text());assert data.get("status")=="passed",data
    payload=data["result"];helper=payload["helper"];poster=Path(payload["posterPath"]);exact=Path(payload["exactPath"])
    base=Path(helper["basePath"]);ov=Path(helper["overlayPath"])
    assert base.is_file() and base.stat().st_size>1024,(label,base)
    assert ov.is_file() and ov.stat().st_size>1024,(label,ov)
    assert poster.is_file() and poster.stat().st_size>1024,(label,poster)
    assert exact.is_file() and exact.stat().st_size>1024,(label,exact)
    # App startup cache cleanup can rotate previews-v3 between isolated QA launches.
    # Preserve the already-validated poster in the QA temp root before launching the next app.
    poster_keep=tmp_root/f"{label}.poster.png"
    shutil.copy2(poster,poster_keep)
    meta=probe(exact);v=next(x for x in meta["streams"] if x.get("codec_type")=="video")
    assert v["width"]==1920 and v["height"]==1080 and v["avg_frame_rate"]=="60/1",(label,v)
    assert "DECODE_VALIDATION=GREEN" in p.stderr,(label,p.stderr[-8000:])
    assert "COMPOSED_FRAME_EXISTS=true" in p.stderr,(label,p.stderr[-8000:])
    assert "BASE_FRAME_EXISTS=true" in p.stderr,(label,p.stderr[-8000:])
    run([FFMPEG,"-hide_banner","-loglevel","error","-stream_loop","19","-i",exact,"-t","60","-map","0:v:0","-f","null","-"],timeout=90)
    return {"exact":exact,"poster":poster,"posterKeep":poster_keep,"helperBase":base,"helperOverlay":ov,"baseKind":helper["baseKind"],"baseBytes":int(helper.get("baseBytes",base.stat().st_size)),"overlayBytes":int(helper.get("overlayBytes",ov.stat().st_size)),"stderr":p.stderr}

def frontend_display(label,preview,effect,preview_type):
    fixture=tmp_root/f"{label}-frontend-fixture.json";result=tmp_root/f"{label}-frontend-result.json"
    fixture.write_text(json.dumps({
      "basePath":str(preview["helperBase"]),"baseKind":preview["baseKind"],"overlayPath":str(preview["helperOverlay"]),"posterPath":str(preview["poster"]),
      "baseBytes":preview["baseBytes"],"overlayBytes":preview["overlayBytes"],"effect":effect,"requestId":label,"previewType":preview_type
    },ensure_ascii=False,indent=2))
    env=os.environ.copy();env.update({"ENDLUME_E2E_FRONTEND_PREVIEW_FIXTURE":str(fixture),"ENDLUME_E2E_FRONTEND_PREVIEW_RESULT":str(result),"ENDLUME_PREVIEW_DIAG":"1"})
    p=subprocess.Popen([str(APP)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
    # WKWebView may defer media decode for a background app. Production Preview is
    # user-visible/foreground, so make the packaged QA app foreground too.
    time.sleep(0.8)
    subprocess.run(["/usr/bin/osascript","-e",'tell application id "studio.endlume.desktop" to activate'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False,timeout=8)
    deadline=time.time()+35
    try:
        while time.time()<deadline and not result.is_file() and p.poll() is None:
            time.sleep(0.1)
        assert result.is_file(),(label,"FRONTEND_RESULT_MISSING",p.poll())
        data=json.loads(result.read_text())
        assert data.get("status")=="GREEN",data
        assert int(data.get("IMAGE_NATURAL_WIDTH",0))==960,data
        assert int(data.get("IMAGE_NATURAL_HEIGHT",0))==540,data
        assert int(data.get("FRONTEND_PAYLOAD_BYTES",0))>1024,data
        assert int(data.get("paintedNonBlack",0))>8,data
        assert data.get("PREVIEW_APPLIED") is True,data
        return data
    finally:
        if p.poll() is None:
            p.terminate()
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill()
        out,err=p.communicate(timeout=5)
        (tmp_root/f"{label}.frontend.stdout").write_text(out or "")
        (tmp_root/f"{label}.frontend.stderr").write_text(err or "")

# Cold app/backend Preview: no Final Render beforehand.
shutil.rmtree(cache_root/"live-preview-v6",ignore_errors=True);shutil.rmtree(cache_root/"previews-v3",ignore_errors=True)
cold_fx=preview_run("cold-effects",[film],[],film["source"])
fx_front=frontend_display("cold-effects-display",cold_fx,film,"Effects")

shutil.rmtree(cache_root/"live-preview-v6",ignore_errors=True);shutil.rmtree(cache_root/"previews-v3",ignore_errors=True)
cold_sub=preview_run("cold-subscribe",[],[sub],sub["source"])
sub_front=frontend_display("cold-subscribe-display",cold_sub,sub,"Subscribe")

baseline=preview_run("baseline",[],[],film["source"])
eq_prev=preview_run("round-equalizer",[eq],[],eq["source"])
third_prev=preview_run("third-effect",[third],[],third["source"])

base_frame=poster_frame(baseline["posterKeep"])
fx_frame=poster_frame(cold_fx["posterKeep"]);sub_frame=poster_frame(cold_sub["posterKeep"]);eq_frame=poster_frame(eq_prev["posterKeep"]);third_frame=poster_frame(third_prev["posterKeep"])
poster_diffs={
    "effects":diff_stats(base_frame,fx_frame),
    "subscribe":diff_stats(base_frame,sub_frame),
    "equalizer":diff_stats(base_frame,eq_frame),
    "third":diff_stats(base_frame,third_frame),
}
# The real 80s film preset is intentionally sparse dust: prove high-delta dust pixels,
# while Subscribe / Equalizer / synthetic third effect must have broad visible coverage.
assert poster_diffs["effects"]["changed"]>=20 and poster_diffs["effects"]["maxDiff"]>=100,poster_diffs["effects"]
for name in ("subscribe","equalizer","third"):
    st=poster_diffs[name]
    assert st["changed"]>=120 and st["meanMaxDiff"]>=0.8,(name,st)
preview_diffs=dict(poster_diffs)

settings={"width":1920,"height":1080,"fps":60,"codec":"h265","bitrateMbps":30.0,"durationHours":2.0,"durationMode":"whole-track","loopMode":"image","crossfadeSec":0.0,"normalizeLufs":False,"outputDir":str(OUT),"preset":"fast","encoderPreference":"auto"}
common_project={"path":str(project),"media":[str(base_media)],"audio":[str(x) for x in songs],"valid":True,"error":None,"anchors":{}}
sub_off=dict(sub);sub_off.update({"enabled":False,"usageMode":"off"})

# Force a fresh Subscribe master so OFF -> ON proves cache invalidation, then repeat ON for HIT/speed.
shutil.rmtree(cache_root/"subscribe-master-v10",ignore_errors=True)

def job(pid,name,subscribes):
    return {"project":dict(common_project,id=pid,name=name),"settings":settings,"effects":[film,eq,third],"subscribes":subscribes,"ambient":None}

jobs=[
    job("e1011-sub-off","ENDLUME 10.0.11 SUB OFF",[sub_off]),
    job("e1011-sub-on","ENDLUME 10.0.11 SUB ON",[sub]),
    job("e1011-sub-warm","ENDLUME 10.0.11 SUB WARM",[sub]),
]
render_fixture=tmp_root/"render-jobs.json";render_result=tmp_root/"render-result.json"
render_fixture.write_text(json.dumps({"jobs":jobs},ensure_ascii=False,indent=2))
env=os.environ.copy();env.update({"ENDLUME_E2E_RENDER_JOB":str(render_fixture),"ENDLUME_E2E_RESULT":str(render_result),"RUST_BACKTRACE":"1"})
started=time.perf_counter();rp=run([APP],check=False,timeout=300,env=env);app_wall=time.perf_counter()-started
(tmp_root/"render.stderr").write_text(rp.stderr);(tmp_root/"render.stdout").write_text(rp.stdout)
assert rp.returncode==0,(rp.returncode,rp.stderr[-12000:])
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
    dur=float(m["format"]["duration"])
    for pos in (1.0,dur/2,max(.5,dur-5)):
        run([FFMPEG,"-hide_banner","-loglevel","error","-ss",str(pos),"-i",p,"-map","0:v:0","-frames:v","2","-f","null","-"],timeout=60)
        run([FFMPEG,"-hide_banner","-loglevel","error","-ss",str(pos),"-i",p,"-map","0:a:0","-t","0.5","-f","null","-"],timeout=60)
    render_meta[pid]={"path":str(p),"wall":float(row["wallSeconds"]),"mib":mib,"duration":dur}

assert render_meta["e1011-sub-warm"]["wall"]<=20.0,("FINAL_RENDER_OVER_20",render_meta["e1011-sub-warm"]["wall"])

diag=[]
for line in rp.stderr.splitlines():
    if "ENDLUME_DIAG " not in line:continue
    try:diag.append(json.loads(line.split("ENDLUME_DIAG ",1)[1].strip()))
    except Exception:pass

recipe=[x for x in diag if x.get("kind")=="subscribe-final-1011"]
assert any(x.get("projectId")=="e1011-sub-on" and x.get("SUBSCRIBE_INCLUDED_IN_RECIPE") is True for x in recipe),recipe[-10:]
on_recipe=next(x for x in recipe if x.get("projectId")=="e1011-sub-on" and x.get("SUBSCRIBE_INCLUDED_IN_RECIPE") is True)
assert on_recipe.get("SUBSCRIBE_ENABLED") is True,on_recipe
assert on_recipe.get("SUBSCRIBE_ASSET_EXISTS") is True,on_recipe
assert abs(float(on_recipe.get("SUBSCRIBE_INTERVAL"))-240.0)<0.01,on_recipe
assert 2.0<=float(on_recipe.get("SUBSCRIBE_DURATION"))<=20.0,on_recipe
ch=on_recipe.get("SUBSCRIBE_CHROMAKEY") or {}
assert abs(float(ch.get("effectiveSimilarity"))-0.10)<0.001,ch
assert abs(float(ch.get("effectiveBlend"))-0.06)<0.001,ch

masters=[x for x in diag if x.get("kind")=="subscribe-master-1011"]
assert any(x.get("projectId")=="e1011-sub-on" and x.get("SUBSCRIBE_MASTER_CREATED") is True and int(x.get("SUBSCRIBE_MASTER_BYTES",0))>1024 for x in masters),masters[-20:]
assert any(x.get("projectId")=="e1011-sub-on" and x.get("SUBSCRIBE_MASTER_CACHE")=="MISS" for x in masters),masters[-20:]
assert any(x.get("projectId")=="e1011-sub-warm" and x.get("SUBSCRIBE_MASTER_CACHE")=="HIT" for x in masters),masters[-20:]
assert all(x.get("SUBSCRIBE_COMPOSITOR_INCLUDED") is True for x in masters if x.get("projectId") in ("e1011-sub-on","e1011-sub-warm")),masters[-20:]

# At t=1s the real schedule is immediate, so ON must visibly differ from OFF.
off_frame=frame(Path(render_meta["e1011-sub-off"]["path"]),1.0)
on_frame=frame(Path(render_meta["e1011-sub-on"]["path"]),1.0)
sub_final_delta=diff_stats(off_frame,on_frame,step_pixels=4,threshold=8)
assert sub_final_delta["changed"]>=120 and sub_final_delta["meanMaxDiff"]>=0.8,sub_final_delta

# Round Equalizer + another ordinary Effect remain present in the accepted ON final.
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
  "status":"GREEN",
  "project":str(project),"library":str(lib_path),"baseMedia":str(base_media),
  "preview":{"effectsBackend":"GREEN","effectsFrontend":fx_front,"subscribeBackend":"GREEN","subscribeFrontend":sub_front,"diffs":preview_diffs,"posterDiffs":poster_diffs},
  "subscribeState":"GREEN","subscribeRecipe":"GREEN","subscribeMaster":"GREEN","subscribeFinal":"GREEN",
  "roundEqualizer":"GREEN","otherEffect":"GREEN","cacheInvalidation":"GREEN",
  "render":render_meta,"subscribeFinalDelta":sub_final_delta,"presence":presence,"appWallSeconds":app_wall,
}
REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print("BACKEND_FRAME=GREEN")
print("FRONTEND_FRAME_DISPLAY=GREEN")
print("COLD_EFFECTS_PREVIEW=GREEN")
print("COLD_SUBSCRIBE_PREVIEW=GREEN")
print("SUBSCRIBE_STATE=GREEN")
print("SUBSCRIBE_RECIPE=GREEN")
print("SUBSCRIBE_MASTER=GREEN")
print("SUBSCRIBE_FINAL=GREEN")
print("ROUND_EQUALIZER=GREEN")
print("OTHER_EFFECT=GREEN")
print("CACHE_INVALIDATION=GREEN")
print("VIDEO=GREEN")
print("AUDIO=GREEN")
print("START_MIDDLE_END=GREEN")
print("RENDER_SECONDS=%.3f" % render_meta["e1011-sub-warm"]["wall"])
print("ENDLUME_1011_PREVIEW_SUBSCRIBE_TARGETED_GREEN")

# Keep ON result for inspection; remove OFF/WARM auxiliaries.
for pid in ("e1011-sub-off","e1011-sub-warm"):
    try:Path(render_meta[pid]["path"]).unlink()
    except Exception:pass
