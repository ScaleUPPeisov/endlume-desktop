#!/usr/bin/env python3
import json, os, subprocess, sys, tempfile
from pathlib import Path

app=Path(sys.argv[1]).resolve()
out_json=Path(sys.argv[2]).resolve()
ff=app/"Contents"/"MacOS"/"ffmpeg"
fp=app/"Contents"/"MacOS"/"ffprobe"
exe_candidates=[p for p in (app/"Contents"/"MacOS").iterdir() if p.is_file() and os.access(p,os.X_OK) and p.name not in ("ffmpeg","ffprobe")]
if len(exe_candidates)!=1:
    raise SystemExit(f"cannot resolve ENDLUME executable: {exe_candidates}")
exe=exe_candidates[0]
for p in (ff,fp,exe):
    if not p.exists():
        raise SystemExit(f"missing runtime: {p}")

root=Path(tempfile.mkdtemp(prefix="endlume-1006-crossfade-"))
img=root/"image.png"
a1=root/"track-1.mp3"
a2=root/"track-2.mp3"
out=root/"out"
out.mkdir()

def run(args, **kw):
    return subprocess.run([str(x) for x in args],check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kw)

run([ff,"-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=0x18233a:s=1920x1080:r=60","-frames:v","1","-y",img])
run([ff,"-hide_banner","-loglevel","error","-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=12","-ac","2","-c:a","libmp3lame","-b:a","320k","-y",a1])
run([ff,"-hide_banner","-loglevel","error","-f","lavfi","-i","sine=frequency=660:sample_rate=48000:duration=12","-ac","2","-c:a","libmp3lame","-b:a","320k","-y",a2])

job={
  "project":{
    "id":"e1006-crossfade-hq320",
    "name":"Crossfade HQ320",
    "path":str(root),
    "media":[str(img)],
    "audio":[str(a1),str(a2)],
    "valid":True,
    "error":None
  },
  "settings":{
    "width":1920,"height":1080,"fps":60,"codec":"h265","bitrateMbps":4.0,
    "durationHours":0.006,"durationMode":"fixed","loopMode":"image","crossfadeSec":2.0,
    "normalizeLufs":False,"outputDir":str(out),"preset":"fast","encoderPreference":"auto"
  },
  "effects":[],"subscribes":[],"ambient":None
}
fixture=root/"job.json"
result=root/"result.json"
fixture.write_text(json.dumps(job,ensure_ascii=False),encoding="utf-8")
env=os.environ.copy()
env["ENDLUME_E2E_RENDER_JOB"]=str(fixture)
env["ENDLUME_E2E_RESULT"]=str(result)
env["RUST_BACKTRACE"]="1"
p=subprocess.run([str(exe)],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=240)
if p.returncode!=0 or not result.exists():
    print(p.stdout)
    print(p.stderr,file=sys.stderr)
    raise SystemExit(f"ENDLUME crossfade render failed rc={p.returncode}, result={result.exists()}")

data=json.loads(result.read_text(encoding="utf-8"))
assert data.get("status")=="passed",data
rows=data.get("results") or []
assert len(rows)==1 and rows[0].get("status")=="passed",rows
row=rows[0]
video=Path(row["outputPath"])
assert video.is_file() and video.stat().st_size>100_000,video

probe=json.loads(run([
    fp,"-v","error","-show_entries",
    "stream=codec_type,codec_name,sample_rate,channels:format=duration",
    "-of","json",video
]).stdout)
vs=next(x for x in probe["streams"] if x.get("codec_type")=="video")
au=next(x for x in probe["streams"] if x.get("codec_type")=="audio")
assert vs.get("codec_name")=="hevc",vs
assert au.get("codec_name")=="aac",au
assert au.get("sample_rate")=="48000",au
assert au.get("channels")==2,au
duration=float(probe["format"]["duration"])
assert duration>=18.0,(duration,probe)
assert row.get("audioMode")=="PROCESSED_AAC",row

summary={
  "kind":"ENDLUME_1006_CROSSFADE_HQ320_RUNTIME_GREEN",
  "output":str(video),
  "bytes":video.stat().st_size,
  "duration":duration,
  "videoCodec":vs.get("codec_name"),
  "audioCodec":au.get("codec_name"),
  "sampleRate":au.get("sample_rate"),
  "channels":au.get("channels"),
  "engineRow":row
}
out_json.parent.mkdir(parents=True,exist_ok=True)
out_json.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False))
