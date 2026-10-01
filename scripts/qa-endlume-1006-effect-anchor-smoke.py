#!/usr/bin/env python3
import json, os, subprocess, sys, tempfile
from pathlib import Path

app=Path(sys.argv[1]).resolve()
ffmpeg=Path(sys.argv[2]).resolve()
ffprobe=Path(sys.argv[3]).resolve()
out_json=Path(sys.argv[4]).resolve()
exe=app/"Contents"/"MacOS"/"endlume"
if not exe.exists():
    candidates=[p for p in (app/"Contents"/"MacOS").iterdir() if p.is_file() and os.access(p,os.X_OK) and p.name not in ("ffmpeg","ffprobe")]
    if len(candidates)!=1:
        raise SystemExit(f"cannot resolve ENDLUME executable: {candidates}")
    exe=candidates[0]

root=Path(tempfile.mkdtemp(prefix="endlume-1006-anchor-"))
img=root/"base.png"
audio=root/"audio.mp3"
overlay=root/"effect.mp4"
output=root/"out"
output.mkdir()

def run_text(args, **kwargs):
    return subprocess.run([str(x) for x in args],check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)

def run_bytes(args, **kwargs):
    return subprocess.run([str(x) for x in args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)

run_text([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=0x18233a:s=1920x1080:r=60","-frames:v","1","-y",img])
run_text([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","sine=frequency=523:sample_rate=48000:duration=9","-ac","2","-c:a","libmp3lame","-b:a","320k","-y",audio])
# 200x200 pure-green plate with a centered 100x100 red subject.
run_text([
    ffmpeg,"-hide_banner","-loglevel","error",
    "-f","lavfi","-i","color=c=0x00ff00:s=200x200:r=60:d=2",
    "-vf","drawbox=x=50:y=50:w=100:h=100:color=0xff0000:t=fill",
    "-an","-c:v","libx264","-preset","ultrafast","-crf","10","-pix_fmt","yuv420p","-y",overlay
])

# Anchor center resolves to (0.35,0.35). Legacy x/y are intentionally far away (0.80,0.80).
job={
  "project":{
    "id":"e1006-anchor-render",
    "name":"ENDLUME 10.0.6 Anchor Render Smoke",
    "path":str(root),
    "media":[str(img)],
    "audio":[str(audio)],
    "valid":True,
    "error":None,
    "anchors":{"FIREPLACE":{"x":0.25,"y":0.40,"source":"manual"}}
  },
  "settings":{
    "width":1920,"height":1080,"fps":60,"codec":"h265","bitrateMbps":4.0,
    "durationHours":0.002,"durationMode":"fixed","loopMode":"image","crossfadeSec":0.0,
    "normalizeLufs":False,"outputDir":str(output),"preset":"fast","encoderPreference":"auto"
  },
  "effects":[{
    "id":"fx-anchor-smoke","name":"Anchor Smoke","source":str(overlay),"enabled":True,
    "mode":"chromakey","keyColor":"#00ff00","similarity":0.12,"blend":0.05,"despill":0.0,
    "lumaThreshold":0.5,"lumaTolerance":0.1,"saturation":1.0,
    "x":0.80,"y":0.80,"scale":0.10,"fullscreen":False,"previewFrameTime":0.0,
    "startSec":0.0,"endSec":None,"cacheKey":None,"cacheReady":None,
    "usageMode":"always","intervalSec":None,"usageDurationSec":None,
    "target":"FIREPLACE","offsetX":0.10,"offsetY":-0.05,"opacity":0.50
  }],
  "subscribes":[],
  "ambient":None
}

fixture=root/"job.json"
result=root/"result.json"
fixture.write_text(json.dumps(job,ensure_ascii=False))
env=os.environ.copy()
env["ENDLUME_E2E_RENDER_JOB"]=str(fixture)
env["ENDLUME_E2E_RESULT"]=str(result)
env["RUST_BACKTRACE"]="1"
p=subprocess.run([str(exe)],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=240)
if p.returncode!=0 or not result.exists():
    print(p.stdout)
    print(p.stderr,file=sys.stderr)
    raise SystemExit(f"ENDLUME anchor render failed rc={p.returncode}, result={result.exists()}")
data=json.loads(result.read_text())
assert data.get("status")=="passed",data
rows=data.get("results") or []
assert len(rows)==1 and rows[0].get("status")=="passed",rows
video=Path(rows[0]["outputPath"])
assert video.is_file() and video.stat().st_size>100_000,video

probe=json.loads(run_text([
    ffprobe,"-v","error","-show_entries",
    "stream=codec_type,codec_name,width,height,avg_frame_rate:format=duration",
    "-of","json",video
]).stdout)
vs=next(x for x in probe["streams"] if x.get("codec_type")=="video")
assert vs.get("codec_name")=="hevc",vs
assert vs.get("width")==1920 and vs.get("height")==1080,vs
assert vs.get("avg_frame_rate")=="60/1",vs

def sample_rgb(cx,cy):
    x=max(0,int(cx)-8);y=max(0,int(cy)-8)
    raw=run_bytes([
        ffmpeg,"-hide_banner","-loglevel","error","-ss","2","-i",video,
        "-vf",f"crop=16:16:{x}:{y},scale=1:1:flags=area,format=rgb24",
        "-frames:v","1","-f","rawvideo","-"
    ]).stdout
    if len(raw)<3:
        raise AssertionError(("pixel sample failed",cx,cy,len(raw)))
    return tuple(raw[:3])

anchor_xy=(round(1920*0.35),round(1080*0.35))
legacy_xy=(round(1920*0.80),round(1080*0.80))
anchor_rgb=sample_rgb(*anchor_xy)
legacy_rgb=sample_rgb(*legacy_xy)

# 50% opaque red subject over dark blue background => red-dominant but not fully opaque.
ar,ag,ab=anchor_rgb
lr,lg,lb=legacy_rgb
assert ar > ab + 35,(anchor_xy,anchor_rgb)
assert 70 < ar < 235,(anchor_xy,anchor_rgb)
# If old x/y were incorrectly used, the legacy location would also become red-dominant.
assert lb >= lr + 10,(legacy_xy,legacy_rgb)

summary={
  "kind":"ENDLUME_1006_EFFECT_ANCHOR_RENDER_PASS",
  "output":str(video),
  "bytes":video.stat().st_size,
  "duration":float(probe["format"]["duration"]),
  "anchorResolved":[0.35,0.35],
  "anchorPixel":list(anchor_rgb),
  "legacyPixel":list(legacy_rgb),
  "opacity":0.50,
  "engineRow":rows[0]
}
out_json.parent.mkdir(parents=True,exist_ok=True)
out_json.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(summary,ensure_ascii=False))
