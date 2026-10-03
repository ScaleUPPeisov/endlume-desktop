#!/usr/bin/env python3
import base64, gzip, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

APP=Path(sys.argv[1])
FFMPEG=Path(sys.argv[2])
FFPROBE=Path(sys.argv[3])
B64=Path(sys.argv[4])
ROOT=Path(sys.argv[5])
raw=gzip.decompress(base64.b64decode(B64.read_text().strip()))
STEAM=ROOT/"exact-steam.mp4"
ROOT.mkdir(parents=True,exist_ok=True)
STEAM.write_bytes(raw)
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

cache_root=Path.home()/"Library/Caches/studio.endlume.desktop"
live_cache=cache_root/"live-preview-v6"
poster_cache=cache_root/"previews-v3"
live_cache.mkdir(parents=True,exist_ok=True)
poster_cache.mkdir(parents=True,exist_ok=True)
base_preview=live_cache/"qa-exact-brewroom-base.png"
poster_black=poster_cache/"qa-exact-black-poster.png"

# Reproduce production prepare_live_preview transport without invoking its QA-only
# second-spawn decode gate. The actual product WebGL LiveCompositePreview remains
# untouched and is what is photographed below.
run([FFMPEG,"-hide_banner","-loglevel","error","-i",base_media,
     "-vf","scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2",
     "-frames:v","1","-compression_level","1","-y",base_preview])
run([FFMPEG,"-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=black:s=960x540:r=1",
     "-frames:v","1","-compression_level","1","-y",poster_black])
assert base_preview.stat().st_size>1024,base_preview.stat().st_size
assert poster_black.stat().st_size>1024,poster_black.stat().st_size

def make_overlay_proxy(t):
    tag=f"{int(t):02d}"
    out=live_cache/f"qa-exact-steam-{tag}.mp4"
    try:out.unlink()
    except FileNotFoundError:pass
    # Diagnostic isolation: keep the product WebGL shader unchanged and force a
    # software H.264 proxy. If WKWebView color becomes correct here, the remaining
    # defect is proven in the VideoToolbox proxy transport/decode path.
    sw=run([FFMPEG,"-hide_banner","-loglevel","error","-stream_loop","-1","-ss",str(float(t)),"-i",STEAM,
            "-t","6","-an","-vf","scale=640:-2:flags=lanczos,fps=60",
            "-c:v","libx264","-preset","ultrafast","-crf","18","-g","1","-keyint_min","1",
            "-sc_threshold","0","-bf","0","-pix_fmt","yuv420p","-movflags","+faststart","-y",out],
           check=False,timeout=120)
    assert sw.returncode==0,(t,sw.stderr[-4000:])
    print(f"EXACT_QA_PROXY_ENCODER_LIBX264_{tag}=GREEN")
    assert out.is_file() and out.stat().st_size>1024,out
    pm=probe(out);pv=next(x for x in pm["streams"] if x.get("codec_type")=="video")
    assert int(pv["width"])==640 and int(pv["height"])==360,pv
    return out

def screenshot(path):
    p=run(["/usr/sbin/screencapture","-x","-m",path],check=False,timeout=20)
    assert p.returncode==0,(p.returncode,p.stderr)
    assert path.is_file() and path.stat().st_size>20_000,path

def frontend_capture(t,overlay,effect):
    tag=f"{int(t):02d}"
    fixture=ROOT/f"frontend-{tag}.json"
    result=ROOT/f"frontend-{tag}-result.json"
    fixture.write_text(json.dumps({
      "basePath":str(base_preview),
      "baseKind":"image",
      "overlayPath":str(overlay),
      "posterPath":str(poster_black),
      "baseBytes":base_preview.stat().st_size,
      "overlayBytes":overlay.stat().st_size,
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
        subprocess.run(["/usr/bin/osascript","-e",'tell application id "studio.endlume.desktop" to activate'],
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False,timeout=8)
        deadline=time.time()+35
        while time.time()<deadline and not result.is_file() and p.poll() is None:
            time.sleep(0.1)
        assert result.is_file(),(t,"FRONTEND_RESULT_MISSING",p.poll())
        data=json.loads(result.read_text())
        assert data.get("status")=="GREEN",data
        assert data.get("PREVIEW_APPLIED") is True,data
        # Result is emitted from actual WebGL readPixels because the intentionally
        # black poster cannot satisfy the non-black poster acceptance gate.
        assert int(data.get("paintedNonBlack",0))>8,data
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
    effect=dict(effect_base);effect["previewFrameTime"]=float(t)
    overlay=make_overlay_proxy(t)
    front,a,b=frontend_capture(t,overlay,effect)
    proxy_a=PREVIEW_DIR/f"proxy-{int(t):02d}-a.png"
    proxy_b=PREVIEW_DIR/f"proxy-{int(t):02d}-b.png"
    run([FFMPEG,"-hide_banner","-loglevel","error","-ss","0.20","-i",overlay,"-frames:v","1","-y",proxy_a])
    run([FFMPEG,"-hide_banner","-loglevel","error","-ss","0.95","-i",overlay,"-frames:v","1","-y",proxy_b])
    assert sha256(proxy_a)!=sha256(proxy_b),(t,"OVERLAY_PROXY_NOT_ANIMATING")
    preview_rows[str(t)]={
      "frontend":front,
      "shotA":str(a),"shotB":str(b),
      "proxyA":str(proxy_a),"proxyB":str(proxy_b),
      "overlayProxy":str(overlay)
    }
    # Persist immediately so a later Final Render infrastructure failure cannot
    # erase the already-captured actual Preview proof.
    (ROOT/"visual-report.json").write_text(json.dumps({
      "status":"PREVIEW_CAPTURED",
      "exactSteam":{"path":str(STEAM),"sha256":sha256(STEAM),"bytes":STEAM.stat().st_size,
                    "width":640,"height":360,"fps":"30/1","duration":dur,"frames":900},
      "brewroom":{"project":str(project),"baseMedia":str(base_media),"audio":str(songs[0])},
      "effect":effect_base,"checkpoints":preview_rows
    },ensure_ascii=False,indent=2))
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
