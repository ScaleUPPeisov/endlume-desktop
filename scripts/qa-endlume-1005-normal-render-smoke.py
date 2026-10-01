#!/usr/bin/env python3
import json, os, subprocess, sys, tempfile
from pathlib import Path

app = Path(sys.argv[1]).resolve()
ffmpeg = Path(sys.argv[2]).resolve()
ffprobe = Path(sys.argv[3]).resolve()
out_json = Path(sys.argv[4]).resolve()
exe = app / "Contents" / "MacOS" / "endlume"
if not exe.exists():
    candidates=[p for p in (app/"Contents"/"MacOS").iterdir() if p.is_file() and os.access(p,os.X_OK) and p.name not in ("ffmpeg","ffprobe")]
    if len(candidates)!=1:
        raise SystemExit(f"cannot resolve ENDLUME executable: {candidates}")
    exe=candidates[0]

root=Path(tempfile.mkdtemp(prefix="endlume-1005-render-"))
img=root/"image.png"
audio=root/"audio.mp3"
output=root/"out"
output.mkdir()

def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)

# Create self-contained media using the exact packaged FFmpeg.
run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=0x18233a:s=1920x1080:r=60","-frames:v","1","-y",img])
run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=12",
     "-ac","2","-c:a","libmp3lame","-b:a","320k","-y",audio])

job={
  "project":{"id":"e1005-normal-render","name":"ENDLUME 10.0.5 Normal Render Smoke","path":str(root),
             "media":[str(img)],"audio":[str(audio)],"valid":True,"error":None},
  "settings":{"width":1920,"height":1080,"fps":60,"codec":"h265","bitrateMbps":4.0,
              "durationHours":0.003,"durationMode":"fixed","loopMode":"image","crossfadeSec":0.0,
              "normalizeLufs":False,"outputDir":str(output),"preset":"fast","encoderPreference":"auto"},
  "effects":[],"subscribes":[],"ambient":None
}
fixture=root/"job.json"
result=root/"result.json"
fixture.write_text(json.dumps(job,ensure_ascii=False))
env=os.environ.copy()
env["ENDLUME_E2E_RENDER_JOB"]=str(fixture)
env["ENDLUME_E2E_RESULT"]=str(result)
env["RUST_BACKTRACE"]="1"
p=subprocess.run([str(exe)],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
if p.returncode!=0:
    print(p.stdout)
    print(p.stderr,file=sys.stderr)
    raise SystemExit(f"packaged ENDLUME render process exited {p.returncode}")
if not result.exists():
    print(p.stdout)
    print(p.stderr,file=sys.stderr)
    raise SystemExit("render result marker missing")
data=json.loads(result.read_text())
assert data.get("status")=="passed",data
rows=data.get("results") or []
assert len(rows)==1,rows
row=rows[0]
assert row.get("status")=="passed",row
video=Path(row["outputPath"])
assert video.is_file() and video.stat().st_size>100_000,(video,video.stat().st_size if video.exists() else 0)
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
  "kind":"ENDLUME_1005_EXACT_ZIP_NORMAL_RENDER_PASS",
  "app":str(app),
  "output":str(video),
  "bytes":video.stat().st_size,
  "duration":duration,
  "videoCodec":vs["codec_name"],
  "resolution":[vs["width"],vs["height"]],
  "fps":vs["avg_frame_rate"],
  "audioCodec":au["codec_name"],
  "audioSampleRate":au["sample_rate"],
  "audioChannels":au["channels"],
  "engineRow":row
}
out_json.parent.mkdir(parents=True,exist_ok=True)
out_json.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(summary,ensure_ascii=False))
