#!/usr/bin/env python3
import json, os, re, subprocess, sys, time
from pathlib import Path

SIDE=Path(sys.argv[1]).resolve()
SUB_FILE=Path(sys.argv[2]).resolve()
APP=Path(sys.argv[3]).resolve()
FFMPEG=Path(sys.argv[4]).resolve()
FFPROBE=Path(sys.argv[5]).resolve()
METRICS=Path(sys.argv[6]).resolve()
OUTPUT_DIR=Path(os.environ.get("ENDLUME_1000_OUTPUT_DIR",str(METRICS.parent/"outputs"))).resolve()
OUTPUT_DIR.mkdir(parents=True,exist_ok=True)

def run(args,**kw):
    return subprocess.run([str(x) for x in args],check=True,**kw)

def out(args):
    return run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout.decode(errors="replace").strip()

def duration(path):
    return float(out([FFPROBE,"-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",path]))

def ffprobe_json(path):
    return json.loads(out([FFPROBE,"-v","error","-show_entries",
      "stream=codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels:format=duration",
      "-of","json",path]))

def seek(path,pos,kind):
    if kind=="video":
        run([FFMPEG,"-hide_banner","-loglevel","error","-ss",f"{pos:.3f}","-i",path,"-map","0:v:0","-frames:v","2","-f","null","-"])
    else:
        run([FFMPEG,"-hide_banner","-loglevel","error","-ss",f"{pos:.3f}","-i",path,"-map","0:a:0","-t","0.4","-f","null","-"])

def max_volume(path,pos):
    p=run([FFMPEG,"-hide_banner","-nostats","-v","info","-ss",f"{pos:.3f}","-i",path,"-map","0:a:0","-t","2.0","-af","volumedetect","-f","null","-"],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    text=p.stderr.decode(errors="replace")
    found=re.findall(r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB",text)
    assert found,(path,pos,text[-2000:])
    return float("-inf") if found[-1]=="-inf" else float(found[-1])

def packet_hashes(path,seconds=5.0,limit=180):
    raw=out([FFPROBE,"-v","error","-select_streams","a:0","-read_intervals",f"%+{seconds}",
      "-show_packets","-show_entries","packet=data_hash","-show_data_hash","sha256","-of","json",path])
    return [p.get("data_hash") for p in json.loads(raw).get("packets") or [] if p.get("data_hash")][:limit]

def assert_packet_copy(source,output):
    src=packet_hashes(source);dst=packet_hashes(output)
    assert len(src)>=8 and len(dst)>=8,(len(src),len(dst))
    for skip in range(0,min(5,len(src)-8)):
        need=src[skip:skip+min(24,len(src)-skip)]
        for start in range(0,max(1,len(dst)-len(need)+1)):
            if dst[start:start+len(need)]==need:return
    raise AssertionError("Original MP3 packet frames are not preserved")

data=json.loads(SIDE.read_text(errors="replace"))
project=data["project"]
media=[Path(x) for x in project.get("media",[]) if Path(x).is_file()]
audio=[Path(x) for x in project.get("audio",[]) if Path(x).is_file()]
effects=[x for x in data.get("effects",[]) if isinstance(x,dict) and x.get("enabled") and Path(str(x.get("source") or "")).is_file()]
assert len(media)>=1,media
assert len(audio)>=15,len(audio)
assert len(effects)>=2,len(effects)

fx=[]
for item in effects[:2]:
    x=dict(item);x["enabled"]=True;x["usageMode"]="always";x["intervalSec"]=240;x["usageDurationSec"]=30
    fx.append(x)

sub=json.loads(SUB_FILE.read_text(errors="replace"))
assert Path(sub["source"]).is_file(),sub
sub.update({
  "enabled":True,
  "usageMode":"interval",
  "intervalSec":240,
  "repeatEverySec":240,
  "firstAppearance":"after-interval",
  "customFirstAtSec":240,
  "showDurationSec":8,
  "firstAtSec":240,
  "secondAtSec":480
})

def make_job(i):
    return {
      "project":{"id":f"e1000-{i}","name":f"ENDLUME 10 warm gate {i}","path":str(SIDE.parent),"media":[str(media[0])],"audio":[str(x) for x in audio[:15]],"valid":True,"error":None},
      "settings":{"width":1920,"height":1080,"fps":60,"codec":"h265","bitrateMbps":4.0,"durationHours":2.0,"durationMode":"whole-track","loopMode":"image","crossfadeSec":0.0,"normalizeLufs":False,"outputDir":str(OUTPUT_DIR),"preset":"fast","encoderPreference":"auto"},
      "effects":fx,"subscribes":[sub],"ambient":None
    }

jobs=[make_job(i) for i in range(1,4)]
fixture=METRICS.parent/"e1000-jobs.json"
result=METRICS.parent/"e1000-result.json"
fixture.write_text(json.dumps({"jobs":jobs},ensure_ascii=False,indent=2))

env=os.environ.copy()
env["ENDLUME_E2E_RENDER_JOB"]=str(fixture)
env["ENDLUME_E2E_RESULT"]=str(result)
env["RUST_BACKTRACE"]="1"
started=time.perf_counter()
proc=subprocess.run([str(APP)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=360)
app_wall=time.perf_counter()-started
if proc.returncode!=0:
    print(proc.stdout)
    print(proc.stderr,file=sys.stderr)
    raise SystemExit(f"ENDLUME 10 E2E exited {proc.returncode}")
raw=json.loads(result.read_text(errors="replace"))
assert raw.get("status")=="passed",raw
rows=raw.get("results") or []
assert len(rows)==3,rows

verified=[]
source=audio[0]
for row in rows:
    assert row.get("status")=="passed",row
    p=Path(row["outputPath"]);assert p.is_file(),p
    size=p.stat().st_size
    assert 500_000_000<=size<=700_000_000,(size,p)
    probe=ffprobe_json(p);fd=float(probe["format"]["duration"])
    video=next(x for x in probe["streams"] if x.get("codec_type")=="video")
    aud=next(x for x in probe["streams"] if x.get("codec_type")=="audio")
    assert video.get("codec_name")=="hevc",video
    assert video.get("width")==1920 and video.get("height")==1080,video
    assert video.get("avg_frame_rate")=="60/1",video
    assert aud.get("codec_name")=="mp3",aud
    assert row.get("audioMode")=="ORIGINAL_MP3_PACKET_COPY",row
    assert_packet_copy(source,p)
    peaks=[max_volume(p,10.0),max_volume(p,max(10.0,fd*.5))]
    assert max(peaks)>-55.0,("SILENT_FINAL_AUDIO",peaks,p)
    for pos in (0.0,fd*.5,max(0.0,fd-2.0)):
        seek(p,pos,"video");seek(p,pos,"audio")
    verified.append({"id":row["id"],"wall_seconds":round(float(row.get("wallSeconds") or 0),3),"bytes":size,"duration":round(fd,3),"peaks_db":peaks,"path":str(p)})

cold=verified[0]["wall_seconds"];warm=[x["wall_seconds"] for x in verified[1:]]
assert cold<=35.0,(cold,"cold > 35s")
assert max(warm)<=15.0,(warm,"warm > 15s")
stderr=proc.stderr
assert '"visualCache":"MISS"' in stderr,stderr[-8000:]
assert '"visualCache":"HIT"' in stderr,stderr[-8000:]
assert '"subscribeCache":"MISS"' in stderr,stderr[-8000:]
assert '"subscribeCache":"HIT"' in stderr,stderr[-8000:]
assert '"kind":"audio-audibility"' in stderr,stderr[-8000:]

metrics={"status":"passed","release_gate":True,"kind":"ENDLUME_1000_REAL_RENDER_JOB","app_wall_seconds":round(app_wall,3),"cold_seconds":cold,"warm_seconds":warm,"results":verified}
METRICS.write_text(json.dumps(metrics,ensure_ascii=False,indent=2))
print("ENDLUME_1000_REAL_RENDER_JOB_GREEN",json.dumps(metrics,ensure_ascii=False))
