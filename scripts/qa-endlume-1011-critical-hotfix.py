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
    best=(None,{"effects":[],"subscribes":[],"ambient":None})
    best_score=-1
    for base in [Path.home()/"Library/Application Support",Path.home()/"Library/Containers"]:
        if not base.exists():continue
        for p in base.rglob("library.json"):
            try:
                if p.stat().st_size>10_000_000:continue
                d=json.load(open(p))
            except Exception:continue
            fx=[x for x in d.get("effects",[]) if isinstance(x,dict) and Path(str(x.get("source",""))).is_file()]
            subs=[x for x in d.get("subscribes",[]) if isinstance(x,dict) and Path(str(x.get("source",""))).is_file()]
            score=len(fx)*10+len(subs)
            if score>best_score:
                best=(p,d);best_score=score
    return best

project,media,songs=resolve_project()
tmp_root=Path(tempfile.mkdtemp(prefix="endlume1011-qa-"))

def app_bundle_root(exe):
    for p in [exe,*exe.parents]:
        if p.suffix.lower()==".app":
            return p
    raise AssertionError(f"PACKAGED_APP_ROOT_NOT_FOUND: {exe}")

APP_BUNDLE=app_bundle_root(APP)
APP_REL=APP.relative_to(APP_BUNDLE)

def fresh_app_binary(label):
    dst=tmp_root/f"{label}.app"
    shutil.rmtree(dst,ignore_errors=True)
    assert APP_BUNDLE.is_dir(),("PACKAGED_APP_SOURCE_MISSING",APP_BUNDLE)
    shutil.copytree(APP_BUNDLE,dst,symlinks=True)
    exe=dst/APP_REL
    assert exe.is_file(),(label,exe)
    return exe

lib_path,lib=load_library()
fx=[dict(x) for x in lib.get("effects",[]) if isinstance(x,dict) and Path(str(x.get("source",""))).is_file()]
subs=[dict(x) for x in lib.get("subscribes",[]) if isinstance(x,dict) and Path(str(x.get("source",""))).is_file()]

def make_overlay(name,key="0x00ff00",shape="red",x=120,y=80):
    src=tmp_root/f"{name}.mp4"
    run([FFMPEG,"-hide_banner","-loglevel","error",
         "-f","lavfi","-i",f"color=c={key}:size=640x360:rate=30","-t","2",
         "-vf",f"drawbox=x={x}:y={y}:w=360:h=160:color={shape}@1:t=fill,drawbox=x={x+70}:y={y+45}:w=220:h=70:color=white@1:t=fill",
         "-c:v","libx264","-preset","ultrafast","-pix_fmt","yuv420p","-y",src],timeout=60)
    return src

def effect_fixture(eid,name,source,**overrides):
    d={"id":eid,"name":name,"source":str(source),"enabled":True,"mode":"chromakey",
       "keyColor":"#00ff00","similarity":0.10,"blend":0.06,"despill":0.35,
       "lumaThreshold":0.03,"lumaTolerance":0.08,"saturation":1.0,
       "x":0.50,"y":0.50,"scale":0.45,"fullscreen":False,"previewFrameTime":0.0,
       "startSec":0.0,"endSec":None,"cacheKey":None,"cacheReady":False,
       "usageMode":"always","intervalSec":240.0,"usageDurationSec":30.0,
       "target":None,"offsetX":None,"offsetY":None,"opacity":1.0}
    d.update(overrides)
    return d

eq=next((x for x in fx if x.get("id")=="825dd7a4-f0cf-4032-a3c9-64290cb5756d" or "эквалайзер круглый" in str(x.get("name","")).lower()),None)
ordinary=[x for x in fx if not eq or x.get("id")!=eq.get("id")]
film=next((x for x in ordinary if any(t in str(x.get("name","")).lower() for t in ("80","плен","пыль","царап"))),ordinary[0] if ordinary else None)
third=next((x for x in ordinary if film is None or x.get("id")!=film.get("id")),None)

if film is None:
    film=effect_fixture("e1011-film","QA 80s Film",make_overlay("qa-film",shape="red",x=55,y=70),
                        x=0.22,y=0.28,scale=0.34,opacity=0.72,similarity=0.08,blend=0.04,despill=0.20)
if eq is None:
    eq=effect_fixture("e1011-eq","QA Round Equalizer",make_overlay("qa-eq",shape="blue",x=145,y=95),
                      x=0.63,y=0.67,scale=0.52,opacity=0.86,similarity=0.13,blend=0.09,despill=0.42)
if third is None:
    third=effect_fixture("e1011-third","QA Third Effect",make_overlay("qa-third",shape="yellow",x=220,y=45),
                         x=0.78,y=0.24,scale=0.27,opacity=0.55,similarity=0.18,blend=0.12,despill=0.60,fullscreen=False)

if subs:
    sub=subs[0]
else:
    sub=effect_fixture("e1011-sub","QA Subscribe",make_overlay("qa-sub",shape="magenta",x=110,y=135),
                       x=0.50,y=0.83,scale=0.42,opacity=1.0,similarity=0.10,blend=0.06,despill=0.35,
                       usageMode="interval",intervalSec=240.0,usageDurationSec=8.0)
    sub.update({"firstAtSec":0.0,"secondAtSec":240.0,"repeatEverySec":240.0,
                "firstAppearance":"immediate","customFirstAtSec":0.0,"showDurationSec":8.0})

background=tmp_root/"background-15m.m4a"
run([FFMPEG,"-hide_banner","-loglevel","error",
     "-f","lavfi","-i","sine=frequency=120:sample_rate=48000:duration=900",
     "-f","lavfi","-i","sine=frequency=1000:sample_rate=48000:duration=900",
     "-f","lavfi","-i","sine=frequency=8000:sample_rate=48000:duration=900",
     "-filter_complex","[0:a][1:a][2:a]amix=inputs=3:normalize=0,volume=0.25",
     "-c:a","aac","-b:a","128k","-ar","48000","-ac","2","-y",background],timeout=90)
background_duration=float(probe(background)["format"]["duration"])
assert 895<=background_duration<=905,background_duration

def always(e):
    x=dict(e);x.update({"enabled":True,"usageMode":"always","startSec":0.0,"endSec":None})
    return x
film=always(film);eq=always(eq);third=always(third)
sub.update({"enabled":True,"usageMode":"interval","intervalSec":240.0,"repeatEverySec":240.0,"firstAppearance":"immediate","customFirstAtSec":0.0,"firstAtSec":0.0,"secondAtSec":240.0,"showDurationSec":8.0,"usageDurationSec":8.0})
e2e_library=tmp_root/"library-e2e.json"
e2e_library.write_text(json.dumps({"effects":[film,eq,third],"subscribes":[sub],"ambient":None},ensure_ascii=False,indent=2))

preview_project=tmp_root/"preview-project";preview_project.mkdir()
base_media=media[0]
link=preview_project/("001"+base_media.suffix.lower())
try:link.symlink_to(base_media)
except Exception:shutil.copy2(base_media,link)

cache_root=Path.home()/"Library/Caches/studio.endlume.desktop"
for name in ("live-preview-v6","previews-v3"):
    shutil.rmtree(cache_root/name,ignore_errors=True)

def persist_preview_payload(label,payload,stderr):
    helper=payload["helper"];exact=Path(payload["exactPath"])
    base=Path(helper["basePath"]);ov=Path(helper["overlayPath"])
    assert base.is_file() and base.stat().st_size>1024,(label,base)
    assert ov.is_file() and ov.stat().st_size>1024,(label,ov)
    assert exact.is_file() and exact.stat().st_size>1024,(label,exact)
    evidence=tmp_root/"preview-evidence"/label;evidence.mkdir(parents=True,exist_ok=True)
    exact_copy=evidence/("exact"+exact.suffix);base_copy=evidence/("base"+base.suffix);overlay_copy=evidence/("overlay"+ov.suffix)
    shutil.copy2(exact,exact_copy);shutil.copy2(base,base_copy);shutil.copy2(ov,overlay_copy)
    meta=probe(exact_copy);v=next(x for x in meta["streams"] if x.get("codec_type")=="video")
    assert v["width"]==1920 and v["height"]==1080 and v["avg_frame_rate"]=="60/1",(label,v)
    run([FFMPEG,"-hide_banner","-loglevel","error","-stream_loop","19","-i",exact_copy,"-t","60","-map","0:v:0","-f","null","-"],timeout=90)
    return {"exact":exact_copy,"helperBase":base_copy,"helperOverlay":overlay_copy,"stderr":stderr}

def preview_run(label,effects,subscribes,overlay):
    fixture=tmp_root/f"{label}-preview-job.json";result=tmp_root/f"{label}-preview-result.json"
    fixture.write_text(json.dumps({"projectPath":str(preview_project),"overlaySource":str(overlay),"timeSec":0.0,"effects":effects,"subscribes":subscribes},ensure_ascii=False,indent=2))
    env=os.environ.copy();env.update({"ENDLUME_E2E_PREVIEW_JOB":str(fixture),"ENDLUME_E2E_RESULT":str(result),"ENDLUME_PREVIEW_DIAG":"1","RUST_BACKTRACE":"1"})
    app_bin=fresh_app_binary(label)
    p=run([app_bin],check=False,timeout=150,env=env)
    (tmp_root/f"{label}.stderr").write_text(p.stderr)
    (tmp_root/f"{label}.stdout").write_text(p.stdout)
    assert p.returncode==0,(label,p.returncode,p.stderr[-5000:])
    data=json.loads(result.read_text());assert data.get("status")=="passed",data
    return persist_preview_payload(label,data["result"],p.stderr)

def preview_batch_run(label,cases):
    fixture=tmp_root/f"{label}-preview-job.json";result=tmp_root/f"{label}-preview-result.json"
    jobs=[]
    for case_label,effects,subscribes,overlay in cases:
        jobs.append({"id":case_label,"projectPath":str(preview_project),"overlaySource":str(overlay),"timeSec":0.0,"effects":effects,"subscribes":subscribes})
    fixture.write_text(json.dumps({"jobs":jobs},ensure_ascii=False,indent=2))
    env=os.environ.copy();env.update({"ENDLUME_E2E_PREVIEW_JOB":str(fixture),"ENDLUME_E2E_RESULT":str(result),"ENDLUME_PREVIEW_DIAG":"1","RUST_BACKTRACE":"1"})
    app_bin=fresh_app_binary(label)
    p=run([app_bin],check=False,timeout=240,env=env)
    (tmp_root/f"{label}.stderr").write_text(p.stderr)
    (tmp_root/f"{label}.stdout").write_text(p.stdout)
    assert p.returncode==0,(label,p.returncode,p.stderr[-5000:])
    data=json.loads(result.read_text());assert data.get("status")=="passed",data
    rows={x["id"]:x["result"] for x in data.get("results",[])}
    assert set(rows)=={x[0] for x in cases},rows.keys()
    return {case_label:persist_preview_payload(case_label,rows[case_label],p.stderr) for case_label,_,_,_ in cases}

# Cold tests remain truly fresh processes. Non-cold preview regressions share one E2E process.
cold_fx=preview_run("cold-effects",[film],[],film["source"])
shutil.rmtree(cache_root/"live-preview-v6",ignore_errors=True);shutil.rmtree(cache_root/"previews-v3",ignore_errors=True)
cold_sub=preview_run("cold-subscribe",[],[sub],sub["source"])
regressions=preview_batch_run("preview-regressions",[
    ("baseline",[],[],film["source"]),
    ("round-equalizer",[eq],[],eq["source"]),
    ("third-effect",[third],[],third["source"]),
])
baseline=regressions["baseline"];eq_prev=regressions["round-equalizer"];third_prev=regressions["third-effect"]

base_frame=frame(baseline["exact"])
film_frame=frame(cold_fx["exact"]);eq_frame=frame(eq_prev["exact"]);third_frame=frame(third_prev["exact"]);sub_frame=frame(cold_sub["exact"])
preview_diffs={
    "film":diff_stats(base_frame,film_frame),
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

def job(pid,name,effects,subscribes=None,ambient=None,ambient_settings=None,settings_override=None):
    cfg=dict(settings)
    if settings_override:cfg.update(settings_override)
    return {
      "project":dict(common_project,id=pid,name=name),
      "settings":cfg,
      "effects":effects,
      "subscribes":[sub] if subscribes is None else subscribes,
      "ambient":ambient,
      "ambientSettings":ambient_settings or {"volumePct":18.0,"bassDb":0.0,"midDb":0.0,"trebleDb":0.0},
    }

stale_film=dict(film);stale_film["source"]=str(tmp_root/"deleted-old-effect-proxy.mp4")
exact_202={"durationHours":2.0+2.0/60.0,"durationMode":"exact","crossfadeSec":0.0,"normalizeLufs":False}
jobs=[
    job("e1011-off","ENDLUME 10.0.11 QA OFF",[film_off,eq,third]),
    job("e1011-on","ENDLUME 10.0.11 QA ON",[film,eq,third]),
    job("e1011-param","ENDLUME 10.0.11 QA PARAM",[param_film,eq,third]),
    job("e1011-warm","ENDLUME 10.0.11 QA WARM",[param_film,eq,third]),
    job("e1011-recover","ENDLUME 10.0.11 QA EFFECT RECOVERY",[stale_film,eq,third]),
    job("e1011-bg-neutral","ENDLUME 10.0.11 QA BG NEUTRAL",[],[],str(background),{"volumePct":20.0,"bassDb":0.0,"midDb":0.0,"trebleDb":0.0},exact_202),
    job("e1011-bg-eq","ENDLUME 10.0.11 QA BG EQ",[],[],str(background),{"volumePct":20.0,"bassDb":-3.0,"midDb":0.0,"trebleDb":-2.0},exact_202),
]
render_fixture=tmp_root/"render-jobs.json";render_result=tmp_root/"render-result.json"
render_fixture.write_text(json.dumps({"jobs":jobs},ensure_ascii=False,indent=2))
env=os.environ.copy();env.update({"ENDLUME_E2E_RENDER_JOB":str(render_fixture),"ENDLUME_E2E_RESULT":str(render_result),"ENDLUME_E2E_LIBRARY_PATH":str(e2e_library),"RUST_BACKTRACE":"1"})
render_app=fresh_app_binary("render-e2e")
started=time.perf_counter();rp=run([render_app],check=False,timeout=300,env=env);app_wall=time.perf_counter()-started
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

cache_events=[]
checkpoints=[]
background_events=[]
recovered_events=[]
for line in rp.stderr.splitlines():
    if "ENDLUME_DIAG " not in line:continue
    try:d=json.loads(line.split("ENDLUME_DIAG ",1)[1].strip())
    except Exception:continue
    if d.get("kind")=="cache" and d.get("visualCacheKey"):cache_events.append(d)
    if d.get("kind")=="eta-checkpoint":checkpoints.append(d)
    if d.get("kind")=="background-music-final":background_events.append(d)
    if d.get("kind")=="render-asset-recovered":recovered_events.append(d)

def keys(pid):
    return {x["visualCacheKey"] for x in cache_events if x.get("projectId")==pid}
ko,k1,kp,kw=keys("e1011-off"),keys("e1011-on"),keys("e1011-param"),keys("e1011-warm")
assert len(ko)==len(k1)==len(kp)==len(kw)==1,(ko,k1,kp,kw)
assert ko!=k1 and k1!=kp and kp==kw,(ko,k1,kp,kw)
assert any(x.get("projectId")=="e1011-warm" and x.get("visualCache")=="HIT" for x in cache_events),cache_events[-20:]

cp={float(x.get("checkpoint",0)):x for x in checkpoints if x.get("projectId")=="e1011-on"}
for c in (50.0,75.0,90.0):assert c in cp,(c,cp)
assert cp[50.0].get("etaSec") is None or float(cp[50.0].get("etaSec"))>0.0,cp[50.0]
assert "::visual-prewarm" not in rp.stderr

for pid in ("e1011-bg-neutral","e1011-bg-eq"):
    assert abs(render_meta[pid]["duration"]-7320.0)<=1.0,(pid,render_meta[pid])
    p=Path(render_meta[pid]["path"])
    for pos in (1.0,905.0,1805.0,3605.0,7315.0):
        run([FFMPEG,"-hide_banner","-loglevel","error","-ss",str(pos),"-i",p,"-map","0:a:0","-t","0.5","-af","volumedetect","-f","null","-"],timeout=60)

bg_by_id={x.get("projectId"):x for x in background_events}
for pid in ("e1011-bg-neutral","e1011-bg-eq"):
    assert pid in bg_by_id,(pid,background_events)
    ev=bg_by_id[pid]
    assert ev.get("loopMode")=="stream_loop" and ev.get("tempPcm") is False,ev
    assert abs(float(ev.get("coveredDuration",0))-7320.0)<=1.0,ev
    assert abs(float(ev.get("volumePct",0))-20.0)<0.01,ev
eq_event=bg_by_id["e1011-bg-eq"]
assert abs(float(eq_event.get("bassDb",99))+3.0)<0.01,eq_event
assert abs(float(eq_event.get("midDb",99))-0.0)<0.01,eq_event
assert abs(float(eq_event.get("trebleDb",99))+2.0)<0.01,eq_event

def pcm_segment(path,pos=30.0,duration=1.0):
    p=subprocess.run([str(FFMPEG),"-hide_banner","-loglevel","error","-ss",str(pos),"-i",str(path),"-map","0:a:0","-t",str(duration),"-ar","48000","-ac","2","-f","s16le","-"],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
    return p.stdout
neutral_pcm=pcm_segment(Path(render_meta["e1011-bg-neutral"]["path"]))
eq_pcm=pcm_segment(Path(render_meta["e1011-bg-eq"]["path"]))
assert len(neutral_pcm)==len(eq_pcm) and len(eq_pcm)>10000
audio_delta=sum(abs(a-b) for a,b in zip(neutral_pcm,eq_pcm))/len(eq_pcm)
assert audio_delta>0.25,audio_delta

assert any(x.get("projectId")=="e1011-recover" and x.get("assetClass")=="EFFECT" and x.get("effectId")==film.get("id") for x in recovered_events),recovered_events

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
  "coldEffectsPreview":"GREEN","coldSubscribePreview":"GREEN","previewDiffs":preview_diffs,
  "processCountBefore":6,"processCountAfter":4,
  "render":render_meta,"cacheKeys":{"off":list(ko)[0],"on":list(k1)[0],"param":list(kp)[0],"warm":list(kw)[0]},
  "cacheInvalidation":"GREEN","progress":"GREEN","eta":"GREEN","filmFinalDelta":film_final_delta,"paramDelta":param_delta,"presence":presence,
  "backgroundMusic":{"status":"GREEN","sourceDuration":background_duration,"coveredDuration":render_meta["e1011-bg-eq"]["duration"],"volumePct":20.0,"bassDb":-3.0,"midDb":0.0,"trebleDb":-2.0,"audioDelta":audio_delta,"tempPcm":False},
  "effectPathRecovery":"GREEN",
  "appWallSeconds":app_wall,
  "qaOutputKept":render_meta["e1011-on"]["path"],
}
REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print("ENDLUME_1011_CRITICAL_HOTFIX_QA_GREEN",json.dumps(report,ensure_ascii=False))

for pid in ("e1011-off","e1011-param","e1011-warm","e1011-recover","e1011-bg-neutral"):
    try:Path(render_meta[pid]["path"]).unlink()
    except Exception:pass