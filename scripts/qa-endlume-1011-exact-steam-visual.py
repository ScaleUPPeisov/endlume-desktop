#!/usr/bin/env python3
import json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

APP=Path(sys.argv[1])
FFMPEG=Path(sys.argv[2])
FFPROBE=Path(sys.argv[3])
STEAM=Path(sys.argv[4])
ROOT=Path(sys.argv[5])
ROOT.mkdir(parents=True,exist_ok=True)
PREVIEW_DIR=ROOT/"preview"
FINAL_DIR=ROOT/"final"
PREVIEW_DIR.mkdir(exist_ok=True)
FINAL_DIR.mkdir(exist_ok=True)

IMAGE={".jpg",".jpeg",".png",".webp",".bmp",".tif",".tiff"}
VIDEO={".mp4",".mov",".m4v",".mkv",".webm",".avi",".wmv",".flv",".ts",".mts",".m2ts",".mpg",".mpeg",".vob",".3gp"}
AUDIO={".mp3",".wav",".m4a",".aac",".flac",".ogg",".opus"}

def run(cmd,check=True,timeout=240,env=None):
    p=subprocess.run([str(x) for x in cmd],capture_output=True,text=True,env=env,timeout=timeout)
    if check and p.returncode!=0:
        raise RuntimeError("CMD_FAIL rc=%s\n%s\n%s"%(p.returncode,p.stdout[-12000:],p.stderr[-12000:]))
    return p

def probe(path):
    p=run([FFPROBE,"-v","error","-show_streams","-show_format","-of","json",path])
    return json.loads(p.stdout)

def sha256(path):
    import hashlib
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

assert STEAM.is_file(),STEAM
assert STEAM.stat().st_size==789147,STEAM.stat().st_size
assert sha256(STEAM)=="d32262025aa7b7ebd2626cfb397b860150104b987957d1c2bf77395016e2cfb0"
meta=probe(STEAM)
v=next(x for x in meta["streams"] if x.get("codec_type")=="video")
assert int(v["width"])==640 and int(v["height"])==360,v
assert v["r_frame_rate"]=="30/1",v
dur=float(meta["format"]["duration"])
assert abs(dur-30.000181)<0.002,dur
frames=run([FFPROBE,"-v","error","-count_frames","-select_streams","v:0","-show_entries","stream=nb_read_frames","-of","csv=p=0",STEAM]).stdout.strip()
assert frames=="900",frames
print("EXACT_STEAM_SOURCE_FOUND=GREEN")
print("EXACT_STEAM_SHA256=GREEN")
print("EXACT_STEAM_MEDIA_CONTRACT=GREEN")

def resolve_brewroom():
    roots=[]
    data_root=Path.home()/"Library/Application Support/studio.endlume.desktop"
    for state_name in ("queue.json","recovery.json"):
        p=data_root/state_name
        if not p.is_file(): continue
        try:d=json.load(open(p))
        except Exception: continue
        jobs=[]
        if isinstance(d,dict):
            if isinstance(d.get("active"),dict): jobs.append(d["active"])
            jobs.extend(x for x in (d.get("pending") or []) if isinstance(x,dict))
        for job in jobs:
            proj=job.get("project") or {}
            hay=" ".join(map(str,[proj.get("name",""),proj.get("path","")])).lower()
            if "brewroom jazz" in hay or "brewroom" in hay:
                q=Path(str(proj.get("path","")))
                if q.is_dir(): roots.append(q)

    for base in [Path("/Volumes/TOSHIBA EXT/ВАЙРОН"),Path.home()/ "Movies",Path.home()/"Documents",Path.home()/"Desktop"]:
        if not base.exists(): continue
        try:
            for p in base.rglob("*"):
                if not p.is_dir(): continue
                s=str(p).lower()
                if "brewroom" in s or p.name.lower()=="новая папка":
                    roots.append(p)
        except Exception:
            pass

    seen=set(); candidates=[]
    for base in roots:
        key=str(base)
        if key in seen: continue
        seen.add(key)
        dirs=[base]
        try: dirs += [p for p in base.rglob("*") if p.is_dir()]
        except Exception: pass
        for d in dirs:
            try: files=[p for p in d.iterdir() if p.is_file() and not p.name.startswith(".") and not p.name.startswith("._")]
            except Exception: continue
            media=sorted([p for p in files if p.suffix.lower() in IMAGE|VIDEO],key=lambda x:x.name.lower())
            songs=sorted([p for p in files if p.suffix.lower() in AUDIO],key=lambda x:x.name.lower())
            if media and songs:
                score=(10 if "brewroom" in str(d).lower() else 0)+min(len(songs),10)
                candidates.append((score,len(songs),-len(str(d)),d,media,songs))
    if not candidates:
        raise AssertionError("BREWROOM_JAZZ_PROJECT_NOT_FOUND")
    _,_,_,project,media,songs=max(candidates)
    return project,media,songs

project,media,songs=resolve_brewroom()
base_media=media[0]
print("BREWROOM_PROJECT="+str(project))
print("BREWROOM_BASE_MEDIA="+str(base_media))
print("BREWROOM_AUDIO="+str(songs[0]))

test_project=ROOT/"brewroom-exact-test-project"
test_project.mkdir(exist_ok=True)
base_link=test_project/("001"+base_media.suffix.lower())
if base_link.exists() or base_link.is_symlink(): base_link.unlink()
try: base_link.symlink_to(base_media)
except Exception: shutil.copy2(base_media,base_link)

effect_base={
  "id":"e1011-exact-steam",
  "name":"Exact Steam Chromakey Acceptance",
  "source":str(STEAM),
  "enabled":True,
  "mode":"chromakey",
  "keyColor":"#00ff00",
  "similarity":0.136,
  "blend":0.35,
  "despill":0.0,
  "lumaThreshold":0.03,
  "lumaTolerance":0.08,
  "saturation":1.0,
  "x":0.637,
  "y":0.316,
  "scale":0.34,
  "fullscreen":False,
  "previewFrameTime":0.0,
  "startSec":0.0,
  "endSec":None,
  "cacheKey":None,
  "cacheReady":False,
  "usageMode":"always",
  "intervalSec":240.0,
  "usageDurationSec":30.0,
  "target":"CUSTOM",
  "offsetX":0.0,
  "offsetY":0.0,
  "opacity":1.0,
}

def preview_backend(t):
    tag=f"{int(t):02d}"
    effect=dict(effect_base);effect["previewFrameTime"]=float(t)
    fixture=ROOT/f"backend-{tag}.json"
    result=ROOT/f"backend-{tag}-result.json"
    fixture.write_text(json.dumps({
      "projectPath":str(test_project),
      "overlaySource":str(STEAM),
      "timeSec":float(t),
      "effects":[effect],
      "subscribes":[]
    },ensure_ascii=False,indent=2))
    env=os.environ.copy()
    env.update({
      "ENDLUME_E2E_PREVIEW_JOB":str(fixture),
      "ENDLUME_E2E_RESULT":str(result),
      "ENDLUME_PREVIEW_DIAG":"1",
      "RUST_BACKTRACE":"1"
    })
    p=run([APP],check=False,timeout=160,env=env)
    (ROOT/f"backend-{tag}.stdout").write_text(p.stdout or "")
    (ROOT/f"backend-{tag}.stderr").write_text(p.stderr or "")
    assert p.returncode==0,(t,p.returncode,p.stderr[-10000:])
    data=json.loads(result.read_text())
    assert data.get("status")=="passed",data
    payload=data["result"]
    for key in ("posterPath","exactPath"):
        src=Path(payload[key]); assert src.is_file() and src.stat().st_size>1024,(t,key,src)
        dst=PREVIEW_DIR/f"{key}-{tag}{src.suffix}"
        shutil.copy2(src,dst)
        payload[key+"Keep"]=str(dst)
    helper=payload["helper"]
    for key in ("basePath","overlayPath"):
        pth=Path(helper[key]); assert pth.is_file() and pth.stat().st_size>1024,(t,key,pth)
    return payload,effect

def screenshot(path):
    p=run(["/usr/sbin/screencapture","-x","-m",path],check=False,timeout=20)
    assert p.returncode==0,(p.returncode,p.stderr)
    assert path.is_file() and path.stat().st_size>20_000,path

def frontend_capture(t,payload,effect):
    tag=f"{int(t):02d}"
    fixture=ROOT/f"frontend-{tag}.json"
    result=ROOT/f"frontend-{tag}-result.json"
    helper=payload["helper"]
    fixture.write_text(json.dumps({
      "basePath":helper["basePath"],
      "baseKind":helper["baseKind"],
      "overlayPath":helper["overlayPath"],
      "posterPath":payload["posterPath"],
      "baseBytes":int(helper.get("baseBytes",0)),
      "overlayBytes":int(helper.get("overlayBytes",0)),
      "effect":effect,
      "requestId":f"exact-steam-{tag}",
      "previewType":"Effects"
    },ensure_ascii=False,indent=2))
    env=os.environ.copy()
    env.update({
      "ENDLUME_E2E_FRONTEND_PREVIEW_FIXTURE":str(fixture),
      "ENDLUME_E2E_FRONTEND_PREVIEW_RESULT":str(result),
      "ENDLUME_PREVIEW_DIAG":"1"
    })
    p=subprocess.Popen([str(APP)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
    try:
        time.sleep(0.8)
        subprocess.run(["/usr/bin/osascript","-e",'tell application id "studio.endlume.desktop" to activate'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False,timeout=8)
        deadline=time.time()+35
        while time.time()<deadline and not result.is_file() and p.poll() is None:
            time.sleep(0.1)
        assert result.is_file(),(t,"FRONTEND_RESULT_MISSING",p.poll())
        data=json.loads(result.read_text())
        assert data.get("status")=="GREEN",data
        assert data.get("PREVIEW_APPLIED") is True,data
        time.sleep(0.35)
        shot0=PREVIEW_DIR/f"preview-{tag}-a.png"
        screenshot(shot0)
        time.sleep(0.75)
        shot1=PREVIEW_DIR/f"preview-{tag}-b.png"
        screenshot(shot1)
        assert sha256(shot0)!=sha256(shot1),(t,"ANIMATION_SCREENSHOTS_IDENTICAL")
        return data,shot0,shot1
    finally:
        if p.poll() is None:
            p.terminate()
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:p.kill()
        out,err=p.communicate(timeout=5)
        (ROOT/f"frontend-{tag}.stdout").write_text(out or "")
        (ROOT/f"frontend-{tag}.stderr").write_text(err or "")

checkpoints=[0,5,10,15,20,25]
preview_rows={}
for t in checkpoints:
    payload,effect=preview_backend(t)
    front,a,b=frontend_capture(t,payload,effect)
    # Extract the first frame of ENDLUME's exact FFmpeg preview as a second parity reference.
    exact=Path(payload["exactPathKeep"])
    exact_png=PREVIEW_DIR/f"ffmpeg-exact-{int(t):02d}.png"
    run([FFMPEG,"-hide_banner","-loglevel","error","-i",exact,"-frames:v","1","-vf","scale=960:540","-y",exact_png])
    preview_rows[str(t)]={
      "frontend":front,
      "shotA":str(a),"shotB":str(b),
      "poster":payload["posterPathKeep"],
      "exactPng":str(exact_png)
    }
    print(f"FRAME_{t}_CAPTURED=GREEN")

# Real 30-second render through render::render_job.
settings={
  "width":1920,"height":1080,"fps":60,"codec":"h265","bitrateMbps":30.0,
  "durationHours":30.0/3600.0,"durationMode":"fixed","loopMode":"image",
  "crossfadeSec":0.0,"normalizeLufs":True,
  "outputDir":str(FINAL_DIR),"preset":"fast","encoderPreference":"auto"
}
render_effect=dict(effect_base);render_effect["previewFrameTime"]=0.0
job={
  "project":{
    "id":"e1011-exact-steam-final",
    "name":"ENDLUME 10.0.11 Exact Steam Final",
    "path":str(test_project),
    "media":[str(base_link)],
    "audio":[str(songs[0])],
    "valid":True,"error":None,"anchors":{}
  },
  "settings":settings,
  "effects":[render_effect],
  "subscribes":[],
  "ambient":None
}
render_fixture=ROOT/"render-job.json"
render_result=ROOT/"render-result.json"
render_fixture.write_text(json.dumps({"jobs":[job]},ensure_ascii=False,indent=2))
env=os.environ.copy()
env.update({"ENDLUME_E2E_RENDER_JOB":str(render_fixture),"ENDLUME_E2E_RESULT":str(render_result),"RUST_BACKTRACE":"1"})
rp=run([APP],check=False,timeout=420,env=env)
(ROOT/"render.stdout").write_text(rp.stdout or "")
(ROOT/"render.stderr").write_text(rp.stderr or "")
assert rp.returncode==0,(rp.returncode,rp.stderr[-16000:])
raw=json.loads(render_result.read_text())
assert raw.get("status")=="passed",raw
row=raw["results"][0]
assert row.get("status")=="passed",row
final_video=Path(row["outputPath"])
assert final_video.is_file() and final_video.stat().st_size>1024,final_video
final_copy=FINAL_DIR/"exact-steam-final.mp4"
if final_video.resolve()!=final_copy.resolve(): shutil.copy2(final_video,final_copy)
fm=probe(final_copy)
fv=next(x for x in fm["streams"] if x.get("codec_type")=="video")
assert fv["codec_name"]=="hevc",(fv,row)
assert int(fv["width"])==1920 and int(fv["height"])==1080,fv
fd=float(fm["format"]["duration"])
assert fd>=29.0,(fd,row)
print("FINAL_RENDER_CREATED=GREEN")

final_frames={}
for t in checkpoints:
    out=FINAL_DIR/f"final-{t:02d}.png"
    run([FFMPEG,"-hide_banner","-loglevel","error","-ss",str(float(t)),"-i",final_copy,"-frames:v","1","-vf","scale=960:540","-y",out])
    assert out.is_file() and out.stat().st_size>20_000,out
    final_frames[str(t)]=str(out)

report={
  "status":"CAPTURED_FOR_VISUAL_REVIEW",
  "exactSteam":{
    "path":str(STEAM),"sha256":sha256(STEAM),"bytes":STEAM.stat().st_size,
    "width":640,"height":360,"fps":"30/1","duration":dur,"frames":900
  },
  "brewroom":{"project":str(project),"baseMedia":str(base_media),"audio":str(songs[0])},
  "effect":effect_base,
  "checkpoints":preview_rows,
  "finalRender":{
    "path":str(final_copy),"duration":fd,"frames":final_frames,
    "videoCodec":fv["codec_name"],"width":fv["width"],"height":fv["height"],
    "wallSeconds":row.get("wallSeconds")
  }
}
(ROOT/"visual-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
print("EXACT_VISUAL_PROOF_CAPTURED=GREEN")
print("VISUAL_REVIEW_REQUIRED=YES")
