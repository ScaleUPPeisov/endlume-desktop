#!/usr/bin/env python3
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

app=Path(sys.argv[1]).resolve()
ffmpeg=Path(sys.argv[2]).resolve()
ffprobe=Path(sys.argv[3]).resolve()
out_json=Path(sys.argv[4]).resolve()
exe=app/"Contents"/"MacOS"/"endlume"
if not exe.exists():
    c=[p for p in (app/"Contents"/"MacOS").iterdir() if p.is_file() and os.access(p,os.X_OK) and p.name not in ("ffmpeg","ffprobe")]
    if len(c)!=1: raise SystemExit(f"cannot resolve ENDLUME executable: {c}")
    exe=c[0]

root=Path(tempfile.mkdtemp(prefix="endlume-1007-prod-"))
base_video=root/"base.mp4"; main_audio=root/"main.mp3"; ambient=root/"ambient.mp3"
fx_on=root/"fx-on.mp4"; fx_off=root/"fx-off.mp4"; sub=root/"subscribe.mp4"; out=root/"out"; out.mkdir()

def run(args, text=True):
    return subprocess.run([str(x) for x in args],check=True,text=text,stdout=subprocess.PIPE,stderr=subprocess.PIPE)

run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=0x18233a:s=1920x1080:r=60:d=9","-an","-c:v","libx264","-preset","ultrafast","-crf","12","-pix_fmt","yuv420p","-y",base_video])
run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=9","-ac","2","-c:a","libmp3lame","-b:a","192k","-y",main_audio])
run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","sine=frequency=880:sample_rate=48000:duration=9","-ac","2","-c:a","libmp3lame","-b:a","128k","-y",ambient])

def overlay(path, color):
    run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=0x00ff00:s=240x240:r=60:d=2",
         "-vf",f"drawbox=x=60:y=60:w=120:h=120:color={color}:t=fill",
         "-an","-c:v","libx264","-preset","ultrafast","-crf","8","-pix_fmt","yuv420p","-y",path])
overlay(fx_on,"0xff0000")
overlay(fx_off,"0xff00ff")
overlay(sub,"0x0080ff")

base_effect={
  "mode":"chromakey","keyColor":"#00ff00","similarity":0.12,"blend":0.04,"despill":0.0,
  "lumaThreshold":0.5,"lumaTolerance":0.1,"saturation":1.0,"fullscreen":False,"previewFrameTime":0.0,
  "startSec":0.0,"endSec":None,"cacheKey":None,"cacheReady":None,"target":"CUSTOM","offsetX":0.0,"offsetY":0.0,"opacity":1.0
}
fx1={"id":"fx-on","name":"ON", "source":str(fx_on),"enabled":True,"x":0.30,"y":0.30,"scale":0.14,
     "usageMode":"always","intervalSec":240.0,"usageDurationSec":30.0,**base_effect}
fx2={"id":"fx-off","name":"OFF", "source":str(fx_off),"enabled":False,"x":0.50,"y":0.50,"scale":0.14,
     "usageMode":"always","intervalSec":240.0,"usageDurationSec":30.0,**base_effect}
sub_effect={"id":"sub","name":"Subscribe","source":str(sub),"enabled":True,"x":0.72,"y":0.70,"scale":0.14,
            "usageMode":"interval","intervalSec":60.0,"usageDurationSec":8.0,**base_effect}
subscribe={**sub_effect,"firstAtSec":60.0,"secondAtSec":120.0,"repeatEverySec":60.0,
           "firstAppearance":"immediate","customFirstAtSec":0.0,"showDurationSec":5.0}

job={
 "project":{"id":"e1007-prod","name":"ENDLUME 10.0.7 Production Smoke","path":str(root),"media":[str(base_video)],"audio":[str(main_audio)],"valid":True,"error":None,"anchors":{}},
 "settings":{"width":1920,"height":1080,"fps":60,"codec":"h265","bitrateMbps":4.0,"durationHours":0.002,
             "durationMode":"exact","loopMode":"original","crossfadeSec":0.0,"normalizeLufs":False,"outputDir":str(out),
             "preset":"fast","encoderPreference":"auto"},
 "effects":[fx1,fx2],"subscribes":[subscribe],"ambient":str(ambient)
}
fixture=root/"job.json"; result=root/"result.json"
fixture.write_text(json.dumps(job,ensure_ascii=False))
env=os.environ.copy(); env["ENDLUME_E2E_RENDER_JOB"]=str(fixture); env["ENDLUME_E2E_RESULT"]=str(result); env["RUST_BACKTRACE"]="1"
p=subprocess.run([str(exe)],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=360)
if p.returncode!=0 or not result.exists():
    print(p.stdout); print(p.stderr,file=sys.stderr); raise SystemExit(f"render failed rc={p.returncode}")
data=json.loads(result.read_text()); assert data.get("status")=="passed",data
rows=data.get("results") or []; assert len(rows)==1 and rows[0].get("status")=="passed",rows
video=Path(rows[0]["outputPath"]); assert video.is_file() and video.stat().st_size>100_000

probe=json.loads(run([ffprobe,"-v","error","-show_entries","stream=codec_type,codec_name,width,height,avg_frame_rate:format=duration","-of","json",video]).stdout)
vs=next(x for x in probe["streams"] if x.get("codec_type")=="video")
assert vs["codec_name"]=="hevc" and vs["width"]==1920 and vs["height"]==1080 and vs["avg_frame_rate"]=="60/1",vs

def rgb(cx,cy,t="2"):
    raw=run([ffmpeg,"-hide_banner","-loglevel","error","-ss",t,"-i",video,"-vf",f"crop=20:20:{int(cx)-10}:{int(cy)-10},scale=1:1:flags=area,format=rgb24","-frames:v","1","-f","rawvideo","-"],text=False).stdout
    assert len(raw)>=3
    return tuple(raw[:3])
on=rgb(1920*.30,1080*.30)
off=rgb(1920*.50,1080*.50)
sb=rgb(1920*.72,1080*.70)
assert on[0] > on[2]+35,("effect ON missing",on)
assert off[2] > off[0]-5 and off[0] < 90,("disabled effect leaked",off)
assert sb[2] > sb[0]+25,("subscribe missing",sb)

def band_mean(freq):
    q=subprocess.run([str(ffmpeg),"-hide_banner","-i",str(video),"-af",f"bandpass=f={freq}:width_type=h:w=35,volumedetect","-f","null","-"],
                     text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stderr
    m=re.search(r"mean_volume:\s*(-?[0-9.]+) dB",q)
    assert m,q[-3000:]
    return float(m.group(1))
main_db=band_mean(440); ambient_db=band_mean(880)
assert main_db>-45,(main_db,ambient_db)
assert ambient_db>-48,(main_db,ambient_db)

summary={"kind":"ENDLUME_1007_PRODUCTION_RENDER_GREEN","video":str(video),"bytes":video.stat().st_size,
         "effectOnPixel":list(on),"effectOffPixel":list(off),"subscribePixel":list(sb),
         "main440MeanDb":main_db,"ambient880MeanDb":ambient_db,"row":rows[0]}
out_json.parent.mkdir(parents=True,exist_ok=True); out_json.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(summary,ensure_ascii=False))
