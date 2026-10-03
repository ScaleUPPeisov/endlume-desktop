#!/usr/bin/env python3
import base64,gzip,hashlib,json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path

APP=Path(sys.argv[1]); FFMPEG=Path(sys.argv[2]); FFPROBE=Path(sys.argv[3]); B64=Path(sys.argv[4]); OUT=Path(sys.argv[5])
OUT.mkdir(parents=True,exist_ok=True)
TIMES=[0,5,10,15,20,25]
IMAGE={".png",".jpg",".jpeg",".webp",".bmp"}
AUDIO={".mp3",".wav",".m4a",".aac",".flac",".ogg",".opus"}
EXPECTED_SHA="d32262025aa7b7ebd2626cfb397b860150104b987957d1c2bf77395016e2cfb0"

def run(cmd,**kw):
    return subprocess.run([str(x) for x in cmd],text=True,capture_output=True,**kw)

def probe(p):
    r=run([FFPROBE,"-v","error","-show_streams","-show_format","-of","json",p],check=True,timeout=30)
    return json.loads(r.stdout)

raw=gzip.decompress(base64.b64decode(B64.read_text().strip()))
steam=OUT/"exact-steam.mp4";steam.write_bytes(raw)
assert hashlib.sha256(raw).hexdigest()==EXPECTED_SHA,"EXACT_STEAM_SHA_MISMATCH"
meta=probe(steam);v=next(x for x in meta["streams"] if x.get("codec_type")=="video")
assert int(v["width"])==640 and int(v["height"])==360,v
assert v.get("r_frame_rate")=="30/1",v
assert int(v.get("nb_frames") or 0)==900,v
assert abs(float(meta["format"]["duration"])-30.000181)<0.01,meta["format"]
print("EXACT_STEAM_SOURCE_FOUND=GREEN",flush=True)

# QA-only launch guard for the self-hosted macOS runner. Direct execution can
# resolve current_exe outside the .app bundle, so mirror the already-packaged
# sidecars beside the QA executable. This does not change product source.
_qa_sidecar_dirs=[APP.parent]
try:
    _release_dir=APP.parents[5]
    if (_release_dir/"endlume").is_file():
        _qa_sidecar_dirs.append(_release_dir)
except IndexError:
    pass
for _dir in _qa_sidecar_dirs:
    for _src,_name in ((FFMPEG,"ffmpeg"),(FFPROBE,"ffprobe")):
        _dst=_dir/_name
        if _src.resolve()!=_dst.resolve():
            shutil.copy2(_src,_dst)
            _dst.chmod(0o755)
for _dir in _qa_sidecar_dirs:
    assert (_dir/"ffmpeg").is_file() and os.access(_dir/"ffmpeg",os.X_OK)
    assert (_dir/"ffprobe").is_file() and os.access(_dir/"ffprobe",os.X_OK)
print("QA_RELEASE_SIDECARS_STAGED=GREEN dirs="+",".join(str(x) for x in _qa_sidecar_dirs),flush=True)

def candidate_dirs():
    out=[]
    data=Path.home()/"Library/Application Support/studio.endlume.desktop"
    for state in ("queue.json","recovery.json"):
        p=data/state
        if not p.is_file(): continue
        try:d=json.load(open(p))
        except Exception:continue
        stack=[]
        if isinstance(d,dict):
            if isinstance(d.get("active"),dict):stack.append(d["active"])
            stack.extend(x for x in d.get("pending",[]) if isinstance(x,dict))
            stack.extend(x for x in d.get("done",[]) if isinstance(x,dict))
        for job in stack:
            proj=job.get("project") or {}
            path=Path(str(proj.get("path","")))
            hay=(str(proj.get("name",""))+" "+str(path)).lower()
            if path.is_dir() and ("brewroom" in hay or "новая папка" in hay):out.append(path)
    for root in (Path("/Volumes/TOSHIBA EXT/ВАЙРОН"),Path.home()/"Desktop",Path.home()/"Documents"):
        if not root.exists():continue
        try:
            for p in root.rglob("*"):
                if p.is_dir() and ("brewroom" in p.name.lower() or p.name.lower()=="новая папка"):
                    out.append(p)
        except Exception:pass
    uniq=[]
    for p in out:
        if p not in uniq:uniq.append(p)
    return uniq

project=None;base=None
for d in candidate_dirs():
    try:files=[p for p in d.iterdir() if p.is_file() and not p.name.startswith(".")]
    except Exception:continue
    imgs=sorted([p for p in files if p.suffix.lower() in IMAGE],key=lambda p:p.name.lower())
    if imgs:
        project=d;base=imgs[0];break
assert project and base,f"BREWROOM_JAZZ_BACKGROUND_NOT_FOUND candidates={candidate_dirs()[:10]}"
print(f"BREWROOM_PROJECT={project}",flush=True)
print(f"BREWROOM_BACKGROUND={base}",flush=True)

tmp=Path(tempfile.mkdtemp(prefix="endlume-1011-exact-steam-"))
preview_project=tmp/"preview-project";preview_project.mkdir()
base_link=preview_project/("001"+base.suffix.lower())
try:base_link.symlink_to(base)
except Exception:shutil.copy2(base,base_link)

effect_base={
 "id":"e1011-exact-steam","name":"Exact Steam Visual QA","source":str(steam),
 "enabled":True,"mode":"chromakey","keyColor":"#00ff00","similarity":0.136,"blend":0.35,"despill":0.0,
 "lumaThreshold":0.03,"lumaTolerance":0.08,"saturation":1.0,
 "x":0.637,"y":0.316,"scale":0.34,"fullscreen":False,"previewFrameTime":0.0,
 "startSec":0.0,"endSec":None,"cacheKey":None,"cacheReady":False,
 "usageMode":"always","intervalSec":240.0,"usageDurationSec":30.0,
 "target":"CUSTOM","offsetX":None,"offsetY":None,"opacity":1.0
}

def backend_preview(t):
    effect=dict(effect_base);effect["previewFrameTime"]=float(t)
    fixture=tmp/f"backend-{t}.json";result=tmp/f"backend-{t}-result.json"
    fixture.write_text(json.dumps({"projectPath":str(preview_project),"overlaySource":str(steam),"timeSec":float(t),"effects":[effect],"subscribes":[]},ensure_ascii=False))
    env=os.environ.copy();env.update({"ENDLUME_E2E_PREVIEW_JOB":str(fixture),"ENDLUME_E2E_RESULT":str(result),"ENDLUME_PREVIEW_DIAG":"1","RUST_BACKTRACE":"1"})
    p=run([APP],env=env,timeout=180)
    (OUT/f"backend-{t:02d}.stderr.txt").write_text(p.stderr)
    assert p.returncode==0,(t,p.returncode,p.stderr[-5000:])
    data=json.loads(result.read_text());assert data.get("status")=="passed",data
    return data["result"],effect

def frontend_shot(t,payload,effect):
    result=OUT/f"frontend-{t:02d}.json"
    fixture=tmp/f"frontend-{t}.json"
    helper=payload["helper"]
    fixture.write_text(json.dumps({
      "basePath":helper["basePath"],"baseKind":helper["baseKind"],"overlayPath":helper["overlayPath"],"posterPath":payload["posterPath"],
      "baseBytes":helper.get("baseBytes",0),"overlayBytes":helper.get("overlayBytes",0),
      "effect":effect,"requestId":f"exact-steam-{t}","previewType":"Effects"
    },ensure_ascii=False))
    env=os.environ.copy();env.update({"ENDLUME_E2E_FRONTEND_PREVIEW_FIXTURE":str(fixture),"ENDLUME_E2E_FRONTEND_PREVIEW_RESULT":str(result),"ENDLUME_PREVIEW_DIAG":"1"})
    p=subprocess.Popen([str(APP)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
    try:
      time.sleep(0.9)
      subprocess.run(["/usr/bin/osascript","-e",'tell application id "studio.endlume.desktop" to activate'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8,check=False)
      deadline=time.time()+30
      while time.time()<deadline and not result.is_file() and p.poll() is None:time.sleep(.1)
      assert result.is_file(),(t,"FRONTEND_RESULT_MISSING",p.poll())
      data=json.loads(result.read_text());assert data.get("status")=="GREEN",data
      time.sleep(1.0)
      shot=OUT/f"preview-{t:02d}.png"
      sc=run(["/usr/sbin/screencapture","-x",shot],timeout=15)
      assert sc.returncode==0 and shot.is_file() and shot.stat().st_size>10000,(t,"SCREENSHOT_FAILED",sc.stderr)
      return data,shot
    finally:
      if p.poll() is None:
        p.terminate()
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:p.kill()
      so,se=p.communicate(timeout=5)
      (OUT/f"frontend-{t:02d}.stdout.txt").write_text(so or "")
      (OUT/f"frontend-{t:02d}.stderr.txt").write_text(se or "")

rows=[]
for t in TIMES:
    payload,effect=backend_preview(t)
    frontend,shot=frontend_shot(t,payload,effect)
    exact=Path(payload["exactPath"]);assert exact.is_file() and exact.stat().st_size>1024
    final_png=OUT/f"final-{t:02d}.png"
    ex=run([FFMPEG,"-hide_banner","-loglevel","error","-i",exact,"-frames:v","1","-y",final_png],timeout=30)
    assert ex.returncode==0 and final_png.is_file() and final_png.stat().st_size>10000,(t,ex.stderr)
    poster=Path(payload["posterPath"])
    if poster.is_file():shutil.copy2(poster,OUT/f"poster-{t:02d}.png")
    rows.append({"time":t,"frontend":frontend,"previewScreenshot":str(shot),"finalScreenshot":str(final_png),"exactPreview":str(exact)})

# Actual animation proof: keyed live proxies generated from six distinct source seeks
# must not be byte-identical frame images.
frame_hashes=[]
for t in TIMES:
    p=OUT/f"poster-{t:02d}.png"
    assert p.is_file(),p
    frame_hashes.append(hashlib.sha256(p.read_bytes()).hexdigest())
assert len(set(frame_hashes))>=5,frame_hashes
print("ANIMATION_SOURCE_CHECK=GREEN",flush=True)

# One real Final Renderer pass, short QA project only.
silent=preview_project/"001.mp3"
rr=run([FFMPEG,"-hide_banner","-loglevel","error","-f","lavfi","-i","anullsrc=r=48000:cl=stereo","-t","31","-c:a","libmp3lame","-b:a","320k","-y",silent],timeout=60)
assert rr.returncode==0 and silent.is_file(),rr.stderr
settings={"width":1920,"height":1080,"fps":60,"codec":"h265","bitrateMbps":30.0,"durationHours":2.0,"durationMode":"whole-track","loopMode":"image","crossfadeSec":0.0,"normalizeLufs":False,"outputDir":str(OUT),"preset":"fast","encoderPreference":"auto"}
project_obj={"id":"e1011-exact-steam-final","name":"Brewroom Jazz Exact Steam QA","path":str(preview_project),"media":[str(base_link)],"audio":[str(silent)],"valid":True,"error":None,"anchors":{}}
render_fixture=tmp/"render.json";render_result=tmp/"render-result.json"
render_fixture.write_text(json.dumps({"jobs":[{"project":project_obj,"settings":settings,"effects":[effect_base],"subscribes":[],"ambient":None}]},ensure_ascii=False))
env=os.environ.copy();env.update({"ENDLUME_E2E_RENDER_JOB":str(render_fixture),"ENDLUME_E2E_RESULT":str(render_result),"RUST_BACKTRACE":"1"})
rp=run([APP],env=env,timeout=360)
(OUT/"final-render.stderr.txt").write_text(rp.stderr)
assert rp.returncode==0,(rp.returncode,rp.stderr[-8000:])
rd=json.loads(render_result.read_text());assert rd.get("status")=="passed",rd
render_path=Path(rd["results"][0]["outputPath"]);assert render_path.is_file(),render_path
for t in TIMES:
    p=OUT/f"render-{t:02d}.png"
    x=run([FFMPEG,"-hide_banner","-loglevel","error","-ss",str(t),"-i",render_path,"-frames:v","1","-y",p],timeout=30)
    assert x.returncode==0 and p.is_file() and p.stat().st_size>10000,(t,x.stderr)
try:render_path.unlink()
except Exception:pass

report={"status":"PROOF_CAPTURED","exactSha256":EXPECTED_SHA,"source":{"width":640,"height":360,"fps":"30/1","frames":900,"duration":float(meta["format"]["duration"])},
        "brewroomProject":str(project),"brewroomBackground":str(base),"effect":effect_base,"frames":rows,"animationDistinctFrames":len(set(frame_hashes)),"finalRender":"GREEN"}
(OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
print("FINAL_RENDER_PASS=GREEN",flush=True)
print("EXACT_STEAM_VISUAL_PROOF_CAPTURED=GREEN",flush=True)
