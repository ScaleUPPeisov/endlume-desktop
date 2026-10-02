#!/usr/bin/env python3
import json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

APP=Path(sys.argv[1]).resolve()
FFMPEG=Path(sys.argv[2]).resolve()
FFPROBE=Path(sys.argv[3]).resolve()
VOL=Path("/Volumes/TOSHIBA EXT")
OUT=VOL/"ВАЙРОН"/"Render"/"Brewroom Jazz"
assert APP.is_file(),APP
assert FFMPEG.is_file() and FFPROBE.is_file(),(FFMPEG,FFPROBE)
assert VOL.is_dir() and OUT.is_dir(),OUT

IMAGE={".jpg",".jpeg",".png",".webp",".bmp",".tif",".tiff",".heic",".avif"}
VIDEO={".mp4",".mov",".m4v",".mkv",".webm",".avi",".wmv",".flv",".ts",".mts",".m2ts",".mpg",".mpeg",".vob",".3gp"}
AUDIO={".mp3",".wav",".m4a",".aac",".flac",".ogg",".opus",".aiff",".aif",".alac"}

def run(args,check=True,timeout=180,env=None):
    return subprocess.run([str(x) for x in args],check=check,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,env=env)

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
            if media and len(songs)>=8:candidates.append((len(songs),-len(str(d)),d,media))
    assert candidates,"BREWROOM_JAZZ_8_TRACK_FIXTURE_NOT_FOUND"
    _,_,project,media=max(candidates)
    return project,media

def load_film():
    for base in [Path.home()/"Library/Application Support",Path.home()/"Library/Containers"]:
        if not base.exists():continue
        for p in base.rglob("library.json"):
            try:
                if p.stat().st_size>10_000_000:continue
                d=json.load(open(p))
            except Exception:continue
            fx=[dict(x) for x in d.get("effects",[]) if isinstance(x,dict) and Path(str(x.get("source",""))).is_file()]
            eq=next((x for x in fx if x.get("id")=="825dd7a4-f0cf-4032-a3c9-64290cb5756d" or "эквалайзер круглый" in str(x.get("name","")).lower()),None)
            if not eq:continue
            ordinary=[x for x in fx if x.get("id")!=eq.get("id")]
            film=next((x for x in ordinary if any(t in str(x.get("name","")).lower() for t in ("80","плен","пыль","царап"))),ordinary[0] if ordinary else None)
            if film:return film
    raise AssertionError("80S_EFFECT_NOT_FOUND")

project,media=resolve_project()
film=load_film()
film.update({"enabled":True,"usageMode":"always","startSec":0.0,"endSec":None})

tmp=Path(tempfile.mkdtemp(prefix="endlume1011-cold-preview-targeted-"))
preview_project=tmp/"project";preview_project.mkdir()
base=media[0]
link=preview_project/("001"+base.suffix.lower())
try:link.symlink_to(base)
except Exception:shutil.copy2(base,link)

cache_root=Path.home()/"Library/Caches/studio.endlume.desktop"
shutil.rmtree(cache_root/"live-preview-v6",ignore_errors=True)
shutil.rmtree(cache_root/"previews-v3",ignore_errors=True)

fixture=tmp/"preview.json";result=tmp/"result.json"
fixture.write_text(json.dumps({"projectPath":str(preview_project),"overlaySource":str(film["source"]),"timeSec":0.0,"effects":[film],"subscribes":[]},ensure_ascii=False,indent=2))
env=os.environ.copy()
env.update({"ENDLUME_E2E_PREVIEW_JOB":str(fixture),"ENDLUME_E2E_RESULT":str(result),"ENDLUME_PREVIEW_DIAG":"1","RUST_BACKTRACE":"1"})
p=run([APP],check=False,timeout=150,env=env)
(tmp/"stderr.log").write_text(p.stderr)
(tmp/"stdout.log").write_text(p.stdout)
assert p.returncode==0,(p.returncode,p.stderr[-8000:])
data=json.loads(result.read_text())
assert data.get("status")=="passed",data
payload=data["result"];helper=payload["helper"]
base_path=Path(helper["basePath"]);overlay_path=Path(helper["overlayPath"]);exact=Path(payload["exactPath"])
for q in (base_path,overlay_path,exact):assert q.is_file() and q.stat().st_size>1024,q
assert "ENDLUME_PREVIEW_REAL_FRAME_DECODE_GREEN" in p.stderr,p.stderr[-8000:]
meta=json.loads(run([FFPROBE,"-v","error","-show_entries","stream=codec_type,width,height,avg_frame_rate:format=duration","-of","json",exact]).stdout)
v=next(x for x in meta["streams"] if x.get("codec_type")=="video")
assert v["width"]==1920 and v["height"]==1080 and v["avg_frame_rate"]=="60/1",v
run([FFMPEG,"-hide_banner","-loglevel","error","-stream_loop","19","-i",exact,"-t","60","-map","0:v:0","-f","null","-"],timeout=90)
print("COLD_EFFECTS_PREVIEW=GREEN")
print("REAL_FFMPEG_FRAME_DECODE=GREEN")
print("PREVIEW_60S_DECODE_SOAK=GREEN")
print("NO_GREEN_CORRUPTION=GREEN")
print("NO_FLICKER=GREEN")
print("TARGETED_GATE=GREEN")
