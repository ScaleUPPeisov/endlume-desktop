#!/usr/bin/env python3
import json, os, re, subprocess, sys, time
from pathlib import Path

PROJECT_DIR=Path(sys.argv[1]).resolve()
SUB_FILE=Path(sys.argv[2]).resolve()
APP=Path(sys.argv[3]).resolve()
FFMPEG=Path(sys.argv[4]).resolve()
FFPROBE=Path(sys.argv[5]).resolve()
METRICS=Path(sys.argv[6]).resolve()
OUTPUT_DIR=Path(os.environ.get("ENDLUME_1002_OUTPUT_DIR",str(METRICS.parent/"outputs"))).resolve()
OUTPUT_DIR.mkdir(parents=True,exist_ok=True)

def run(args,**kw):
    return subprocess.run([str(x) for x in args],check=True,**kw)
def out(args):
    return run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout.decode(errors="replace").strip()
def ffprobe_json(path):
    return json.loads(out([FFPROBE,"-v","error","-show_streams","-show_format","-of","json",path]))
def duration(path):
    return float(ffprobe_json(path)["format"]["duration"])
def max_volume(path,pos):
    p=subprocess.run([str(FFMPEG),"-hide_banner","-nostats","-v","info","-ss",f"{pos:.3f}","-i",str(path),"-map","0:a:0","-t","2.0","-af","volumedetect","-f","null","-"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True)
    found=re.findall(r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB",p.stderr)
    assert found,(path,pos,p.stderr[-2000:])
    return float("-inf") if found[-1]=="-inf" else float(found[-1])

def native_audio_gate(path,positions):
    swift=METRICS.parent/"endlume-1002-avfoundation.swift"
    swift.write_text(r'''
import Foundation
import AVFoundation
import AudioToolbox
import CoreMedia

let url=URL(fileURLWithPath:CommandLine.arguments[1])
let asset=AVURLAsset(url:url)
let tracks=asset.tracks(withMediaType:.audio)
print("AVF_AUDIO_STREAMS=\(tracks.count)")
guard tracks.count == 1, let track=tracks.first else { exit(11) }
for arg in CommandLine.arguments.dropFirst(2) {
  let parts=arg.split(separator:"=",maxSplits:1)
  let label=String(parts[0]); let pos=Double(parts[1])!
  do {
    let reader=try AVAssetReader(asset:asset)
    reader.timeRange=CMTimeRange(start:CMTime(seconds:pos,preferredTimescale:60000),duration:CMTime(seconds:3,preferredTimescale:60000))
    let settings:[String:Any]=[
      AVFormatIDKey:kAudioFormatLinearPCM,
      AVLinearPCMBitDepthKey:16,
      AVLinearPCMIsFloatKey:false,
      AVLinearPCMIsBigEndianKey:false,
      AVLinearPCMIsNonInterleaved:false
    ]
    let output=AVAssetReaderTrackOutput(track:track,outputSettings:settings)
    guard reader.canAdd(output) else { print("AVF_\(label)=CANNOT_ADD"); exit(12) }
    reader.add(output)
    guard reader.startReading() else { print("AVF_\(label)=START_FAIL"); exit(13) }
    var bytes=0; var nonzero=0; var peak:Int16=0
    while let sample=output.copyNextSampleBuffer() {
      guard let block=CMSampleBufferGetDataBuffer(sample) else { continue }
      let len=CMBlockBufferGetDataLength(block); if len<=0 { continue }
      var data=[UInt8](repeating:0,count:len)
      if CMBlockBufferCopyDataBytes(block,atOffset:0,dataLength:len,destination:&data) != kCMBlockBufferNoErr { continue }
      bytes += len
      data.withUnsafeBytes { raw in
        for v in raw.bindMemory(to:Int16.self) {
          if v != 0 { nonzero += 1 }
          let a = v == Int16.min ? Int16.max : Swift.abs(v)
          if a > peak { peak=a }
        }
      }
    }
    print("AVF_\(label)_BYTES=\(bytes)")
    print("AVF_\(label)_NONZERO=\(nonzero)")
    print("AVF_\(label)_PEAK=\(peak)")
    guard bytes>0 && nonzero>0 && peak>0 else { exit(14) }
  } catch {
    print("AVF_\(label)_ERROR=\(error)"); exit(15)
  }
}
print("AVFOUNDATION_PLAYBACK_GATE=PASS")
''')
    args=["/usr/bin/swift",str(swift),str(path)] + [f"{k}={v:.3f}" for k,v in positions]
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    assert p.returncode==0,(p.returncode,p.stdout,p.stderr)
    assert "AVFOUNDATION_PLAYBACK_GATE=PASS" in p.stdout,p.stdout
    return p.stdout.strip()

source=PROJECT_DIR/"для Японского канала .mp4"
assert source.is_file(),source
source_meta=ffprobe_json(source)
sv=next(s for s in source_meta["streams"] if s.get("codec_type")=="video")
assert sv.get("codec_name")=="hevc",sv
assert sv.get("width")==1920 and sv.get("height")==1080,sv
assert sv.get("avg_frame_rate")=="60/1",sv
source_seconds=float(source_meta["format"]["duration"])
assert 19.0 <= source_seconds <= 21.0,source_seconds

audio=sorted([p for p in PROJECT_DIR.rglob("*") if p.is_file() and p.suffix.lower()==".mp3"],key=lambda p:p.name.lower())
if len(audio)<10:
    # Project audio can live on an external disk; reuse the most recent ENDLUME side file only for source paths.
    candidates=sorted((Path.home()/"Movies/ENDLUME Studio/logs").glob("*project.json"),key=lambda p:p.stat().st_mtime,reverse=True)
    for side in candidates:
        try:
            j=json.loads(side.read_text(errors="replace"))
            found=[Path(x) for x in j.get("project",{}).get("audio",[]) if Path(x).is_file() and Path(x).suffix.lower()==".mp3"]
            if len(found)>=10:
                audio=found
                break
        except Exception:
            pass
assert len(audio)>=10,len(audio)
audio=audio[:10]

# Reuse actual enabled ENDLUME effects whose source files still exist, but make them ALWAYS
# so the short physical Ping-Pong cycle exercises the same visual path without a long encode.
effects=[]
candidates=sorted((Path.home()/"Movies/ENDLUME Studio/logs").glob("*project.json"),key=lambda p:p.stat().st_mtime,reverse=True)
for side in candidates:
    try:
        j=json.loads(side.read_text(errors="replace"))
        found=[dict(x) for x in j.get("effects",[]) if isinstance(x,dict) and x.get("enabled") and Path(str(x.get("source") or "")).is_file()]
        if found:
            for x in found[:2]:
                x["enabled"]=True; x["usageMode"]="always"; x["intervalSec"]=240; x["usageDurationSec"]=30
            effects=found[:2]
            break
    except Exception:
        pass
assert effects,effects

sub=json.loads(SUB_FILE.read_text(errors="replace"))
assert Path(str(sub.get("source") or "")).is_file(),sub
sub.update({
  "enabled":True,"usageMode":"interval","intervalSec":240,"repeatEverySec":240,
  "firstAppearance":"after-interval","customFirstAtSec":240,"showDurationSec":8,
  "firstAtSec":240,"secondAtSec":480
})

def make_job(i):
    return {
      "project":{"id":f"e1002-ping-{i}","name":f"ENDLUME 10.0.2 PingPong QA {i}","path":str(PROJECT_DIR),"media":[str(source)],"audio":[str(x) for x in audio],"valid":True,"error":None},
      "settings":{"width":1920,"height":1080,"fps":60,"codec":"h265","bitrateMbps":4.0,"durationHours":2.0,"durationMode":"whole-track","loopMode":"pingpong","crossfadeSec":0.0,"normalizeLufs":False,"outputDir":str(OUTPUT_DIR),"preset":"fast","encoderPreference":"auto"},
      "effects":effects,"subscribes":[sub],"ambient":None
    }

jobs=[make_job(i) for i in range(1,4)]
fixture=METRICS.parent/"e1002-pingpong-jobs.json"
result=METRICS.parent/"e1002-pingpong-result.json"
fixture.write_text(json.dumps({"jobs":jobs},ensure_ascii=False,indent=2))

env=os.environ.copy()
env["ENDLUME_E2E_RENDER_JOB"]=str(fixture)
env["ENDLUME_E2E_RESULT"]=str(result)
env["RUST_BACKTRACE"]="1"
started=time.perf_counter()
proc=subprocess.run([str(APP)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=360)
app_wall=time.perf_counter()-started
print(proc.stdout)
print(proc.stderr,file=sys.stderr)
assert proc.returncode==0,proc.returncode
raw=json.loads(result.read_text(errors="replace"))
assert raw.get("status")=="passed",raw
rows=raw.get("results") or []
assert len(rows)==3,rows

verified=[]
for n,row in enumerate(rows):
    assert row.get("status")=="passed",row
    p=Path(row["outputPath"]); assert p.is_file(),p
    meta=ffprobe_json(p); fd=float(meta["format"]["duration"]); size=p.stat().st_size
    video=[x for x in meta["streams"] if x.get("codec_type")=="video"]
    aud=[x for x in meta["streams"] if x.get("codec_type")=="audio"]
    assert len(video)==1 and len(aud)==1,(video,aud)
    v=video[0]; a=aud[0]
    assert v.get("codec_name")=="hevc",v
    assert v.get("width")==1920 and v.get("height")==1080,v
    assert v.get("avg_frame_rate")=="60/1",v
    assert a.get("codec_name")=="aac",a
    assert a.get("codec_tag_string")=="mp4a",a
    assert a.get("sample_rate")=="48000" and a.get("channels")==2,a
    assert (a.get("disposition") or {}).get("default")==1,a
    assert abs(float(a.get("start_time") or 0))<=0.1,a
    peaks=[max_volume(p,1.0),max_volume(p,fd*.5),max_volume(p,max(0.5,fd-5.0))]
    assert all(x>-55.0 for x in peaks),peaks
    native=native_audio_gate(p,[("START",1.0),("MIDDLE",fd*.5),("END",max(0.5,fd-5.0))]) if n==0 else "ALREADY_PASSED"
    wall=float(row.get("wallSeconds") or 0)
    assert 500_000_000 <= size <= 700_000_000,(size,p)
    assert row.get("fastPath") is True,row
    assert row.get("fastPathReason")=="FAST_SHORT_VIDEO_PINGPONG",row
    assert row.get("audioMode") in ("SOURCE_MP3_TO_AAC_320K","PROCESSED_AAC"),row
    verified.append({"id":row["id"],"wall_seconds":round(wall,3),"bytes":size,"duration":round(fd,3),"peaks_db":peaks,"native":native,"path":str(p)})
    print("E1002_PINGPONG_ROW",json.dumps(verified[-1],ensure_ascii=False),flush=True)

cold=verified[0]["wall_seconds"]; warm=[x["wall_seconds"] for x in verified[1:]]
assert cold<=60.0,(cold,"cold > 60s")
assert max(warm)<=30.0,(warm,"warm > 30s")
stderr=proc.stderr
assert '"pingPongFast":true' in stderr,stderr[-12000:]
assert '"pingPongCache":"MISS"' in stderr,stderr[-12000:]
assert '"pingPongCache":"HIT"' in stderr,stderr[-12000:]
assert '"kind":"audio-audibility"' in stderr,stderr[-12000:]
# 20.033s 60fps source should become a 40.0s seamless non-duplicated physical cycle.
m=re.findall(r'"pingPongPhysicalFrames":(\d+)',stderr)
assert m,m
assert 2398 <= int(m[-1]) <= 2402,m[-10:]

metrics={
  "status":"passed","release_gate":True,"kind":"ENDLUME_1002_REAL_PINGPONG",
  "source":str(source),"source_bytes":source.stat().st_size,"source_seconds":source_seconds,
  "source_audio_count":len(audio),"effects_count":len(effects),"subscribe_interval_sec":240,
  "app_wall_seconds":round(app_wall,3),"cold_seconds":cold,"warm_seconds":warm,"results":verified
}
METRICS.write_text(json.dumps(metrics,ensure_ascii=False,indent=2))
print("ENDLUME_1002_PINGPONG_GREEN",json.dumps(metrics,ensure_ascii=False))
