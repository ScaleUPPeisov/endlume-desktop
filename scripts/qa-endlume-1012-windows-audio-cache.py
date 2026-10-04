#!/usr/bin/env python3
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

app=Path(sys.argv[1]).resolve()
ffmpeg=Path(sys.argv[2]).resolve()
ffprobe=Path(sys.argv[3]).resolve()
report=Path(sys.argv[4]).resolve()
for p in (app,ffmpeg,ffprobe):
    if not p.is_file():
        raise SystemExit(f"missing: {p}")

root=Path(tempfile.mkdtemp(prefix="endlume-1012-windows-audio-"))
out=root/"outputs";out.mkdir()
img=root/"image.png"

def run(args,**kw):
    return subprocess.run([str(x) for x in args],check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kw)

def probe(path):
    return json.loads(run([ffprobe,"-v","error","-show_entries",
        "stream=codec_type,codec_name,sample_rate,channels:format=duration","-of","json",path]).stdout)

run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=0x18233a:s=1920x1080:r=60","-frames:v","1","-y",img])

wav_long=root/"long.wav"
wav_short=root/"short.wav"
mp3_48=root/"base48.mp3"
mp3_44=root/"base44.mp3"
fake_mp3=root/"fake-pcm.mp3"
run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","sine=frequency=330:sample_rate=48000:duration=4","-ac","2","-c:a","pcm_s16le","-y",wav_long])
run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=4","-ac","2","-c:a","pcm_s16le","-y",wav_short])
run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","sine=frequency=550:sample_rate=48000:duration=4","-ac","2","-c:a","libmp3lame","-b:a","320k","-y",mp3_48])
run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","sine=frequency=660:sample_rate=44100:duration=4","-ac","2","-c:a","libmp3lame","-b:a","320k","-y",mp3_44])
run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","sine=frequency=770:sample_rate=48000:duration=4","-ac","2","-c:a","pcm_s16le","-f","wav","-y",fake_mp3])
tiny_wav=root/"tiny.wav"
run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","sine=frequency=880:sample_rate=48000:duration=0.6","-ac","2","-c:a","pcm_s16le","-y",tiny_wav])

wav20=[]
for i in range(20):
    p=root/f"pressure-{i:02}.wav";shutil.copy2(wav_long,p);wav20.append(p)
mp320=[]
for i in range(20):
    p=root/f"mp3-{i:02}.mp3";shutil.copy2(mp3_48,p);mp320.append(p)

def job(pid,name,audio,crossfade,project_path=None,duration_hours=0.003):
    project_path=Path(project_path or root)
    return {
      "project":{"id":pid,"name":name,"path":str(project_path),"media":[str(img)],"audio":[str(x) for x in audio],"valid":True,"error":None},
      "settings":{"width":1920,"height":1080,"fps":60,"codec":"h265","bitrateMbps":4.0,
                  "durationHours":duration_hours,"durationMode":"fixed","loopMode":"image","crossfadeSec":crossfade,
                  "normalizeLufs":False,"outputDir":str(out),"preset":"fast","encoderPreference":"auto"},
      "effects":[],"subscribes":[],"ambient":None
    }

jobs=[
  job("e1012-a-20wav","E1012 A 20 WAV cache pressure",wav20,0.0),
  job("e1012-b-20mp3","E1012 B 20 compatible MP3",mp320,0.0),
  job("e1012-c-mixed","E1012 C mixed fallback",[mp3_48,wav_short,fake_mp3,mp3_44],0.0),
  job("e1012-d-1mp3","E1012 D one MP3",[mp3_48],0.0),
]

# Realistic customer queue: 40 distinct project directories, each with 20 decodable
# WAV inputs. Durations are intentionally tiny so CI exercises scan/localization/audio
# planning/FFmpeg-open/queue handoff without producing 40 long customer videos.
batch40=root/"batch40";batch40.mkdir()
for project_no in range(40):
    project_dir=batch40/f"project-{project_no:02}"
    project_dir.mkdir()
    tracks=[]
    for track_no in range(20):
        track=project_dir/f"track-{track_no:02}.wav"
        shutil.copy2(tiny_wav,track)
        tracks.append(track)
    jobs.append(job(
        f"e1012-q40-{project_no:02}",
        f"E1012 Queue40 {project_no:02}",
        tracks,
        0.0,
        project_path=project_dir,
        duration_hours=0.0003,
    ))
fixture=root/"jobs.json";result=root/"result.json"
fixture.write_text(json.dumps({"jobs":jobs},ensure_ascii=False,indent=2),encoding="utf-8")
env=os.environ.copy();env["ENDLUME_E2E_RENDER_JOB"]=str(fixture);env["ENDLUME_E2E_RESULT"]=str(result);env["RUST_BACKTRACE"]="1"
started=time.perf_counter()
p=subprocess.run([str(app)],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=1800)
wall=time.perf_counter()-started
if p.returncode!=0:
    print(p.stdout);print(p.stderr,file=sys.stderr);raise SystemExit(f"ENDLUME exited {p.returncode}")
if not result.is_file():
    print(p.stdout);print(p.stderr,file=sys.stderr);raise SystemExit("E2E result missing")
data=json.loads(result.read_text(encoding="utf-8"))
assert data.get("status")=="passed",data
rows=data.get("results") or []
assert len(rows)==44,rows
by_id={r.get("id"):r for r in rows}
for j in jobs:
    row=by_id.get(j["project"]["id"]);assert row and row.get("status")=="passed",(j["project"]["id"],row)

assert by_id["e1012-a-20wav"].get("audioMode")=="PROCESSED_AAC",by_id["e1012-a-20wav"]
assert by_id["e1012-c-mixed"].get("audioMode")=="PROCESSED_AAC",by_id["e1012-c-mixed"]
assert by_id["e1012-b-20mp3"].get("audioMode")=="SOURCE_MP3_TO_AAC_320K",by_id["e1012-b-20mp3"]
assert by_id["e1012-d-1mp3"].get("audioMode")=="SOURCE_MP3_TO_AAC_320K",by_id["e1012-d-1mp3"]
for project_no in range(40):
    row=by_id[f"e1012-q40-{project_no:02}"]
    assert row.get("audioMode")=="PROCESSED_AAC",row

verified=[]
for row in rows:
    video=Path(row["outputPath"]);assert video.is_file() and video.stat().st_size>100_000,video
    meta=probe(video)
    au=next(x for x in meta["streams"] if x.get("codec_type")=="audio")
    assert au.get("codec_name")=="aac",au
    assert au.get("sample_rate")=="48000",au
    assert au.get("channels")==2,au
    verified.append({"id":row.get("id"),"audioMode":row.get("audioMode"),"bytes":video.stat().st_size,
                     "duration":float(meta["format"]["duration"]),"output":str(video)})

stderr=p.stderr
if "processed-audio-local-v1008" in stderr and "No such file or directory" in stderr:
    raise AssertionError("processed audio cache input disappeared")
assert "Strict Fidelity: исходную музыку нельзя сохранить bitstream-copy" not in stderr,stderr[-8000:]

summary={"status":"GREEN","kind":"ENDLUME_1012_WINDOWS_AUDIO_CACHE_QA","wallSeconds":round(wall,3),
         "cachePressure20Wav":"GREEN","compatible20Mp3":"GREEN","mixedFallback":"GREEN","oneTrack":"GREEN",
         "queueHandoff":"GREEN","realistic40ProjectQueue":"GREEN","results":verified}
report.parent.mkdir(parents=True,exist_ok=True)
report.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False))
