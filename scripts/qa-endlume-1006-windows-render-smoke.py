#!/usr/bin/env python3
import json, os, subprocess, sys, tempfile
from pathlib import Path

exe=Path(sys.argv[1]).resolve()
ffmpeg=Path(sys.argv[2]).resolve()
ffprobe=Path(sys.argv[3]).resolve()
out_json=Path(sys.argv[4]).resolve()
for p in (exe,ffmpeg,ffprobe):
    if not p.exists():
        raise SystemExit(f"missing: {p}")

root=Path(tempfile.mkdtemp(prefix="endlume-1006-win-render-"))
img=root/"image.png"
audio=root/"audio.mp3"
output=root/"out"
output.mkdir()

def run(args, **kwargs):
    return subprocess.run([str(x) for x in args],check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)

run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=0x18233a:s=1920x1080:r=60","-frames:v","1","-y",img])
run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=12",
     "-ac","2","-c:a","libmp3lame","-b:a","320k","-y",audio])

job={
  "project":{"id":"e1006-win-normal-render","name":"ENDLUME 10.0.6 Windows Normal Render Smoke","path":str(root),
             "media":[str(img)],"audio":[str(audio)],"valid":True,"error":None},
  "settings":{"width":1920,"height":1080,"fps":60,"codec":"h265","bitrateMbps":4.0,
              "durationHours":0.003,"durationMode":"fixed","loopMode":"image","crossfadeSec":0.0,
              "normalizeLufs":False,"outputDir":str(output),"preset":"fast","encoderPreference":"auto"},
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
if p.returncode!=0:
    print(p.stdout)
    print(p.stderr,file=sys.stderr)
    raise SystemExit(f"ENDLUME render process exited {p.returncode}")
if not result.exists():
    print(p.stdout)
    print(p.stderr,file=sys.stderr)
    raise SystemExit("render result marker missing")
data=json.loads(result.read_text(encoding="utf-8"))
assert data.get("status")=="passed",data
rows=data.get("results") or []
assert len(rows)==1 and rows[0].get("status")=="passed",rows
video=Path(rows[0]["outputPath"])
assert video.is_file() and video.stat().st_size>100_000,video
probe=json.loads(run([ffprobe,"-v","error","-show_entries",
                      "stream=codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels:format=duration",
                      "-of","json",video]).stdout)
vs=next(x for x in probe["streams"] if x.get("codec_type")=="video")
au=next(x for x in probe["streams"] if x.get("codec_type")=="audio")
assert vs.get("codec_name")=="hevc",vs
assert vs.get("width")==1920 and vs.get("height")==1080,vs
assert vs.get("avg_frame_rate")=="60/1",vs
assert au.get("codec_name")=="aac",au
assert au.get("sample_rate")=="48000",au
assert au.get("channels")==2,au
duration=float(probe["format"]["duration"])
assert duration>=9.0,(duration,probe)
summary={
  "kind":"ENDLUME_1006_WINDOWS_NORMAL_RENDER_PASS",
  "exe":str(exe),"output":str(video),"bytes":video.stat().st_size,"duration":duration,
  "videoCodec":vs["codec_name"],"resolution":[vs["width"],vs["height"]],"fps":vs["avg_frame_rate"],
  "audioCodec":au["codec_name"],"audioSampleRate":au["sample_rate"],"audioChannels":au["channels"],
  "engineRow":rows[0]
}
out_json.parent.mkdir(parents=True,exist_ok=True)
out_json.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False))
