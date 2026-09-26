#!/usr/bin/env python3
import hashlib, json, os, subprocess, sys, tempfile, time
from pathlib import Path

SIDE=Path(sys.argv[1]).resolve()
APP=Path(sys.argv[2]).resolve()
FFMPEG=Path(sys.argv[3]).resolve()
FFPROBE=Path(sys.argv[4]).resolve()
METRICS=Path(sys.argv[5] if len(sys.argv)>5 else "865-render-job-e2e.json").resolve()

def run(args,**kw):
    return subprocess.run([str(x) for x in args],check=True,**kw)

def out(args):
    return run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout.decode(errors="replace").strip()

def ffprobe_json(path):
    return json.loads(out([FFPROBE,"-v","error","-show_entries",
        "stream=codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels:format=duration",
        "-of","json",path]))

def seek(path,pos,kind):
    if kind=="video":
        run([FFMPEG,"-hide_banner","-loglevel","error","-ss",f"{pos:.3f}","-i",path,"-map","0:v:0","-frames:v","2","-f","null","-"])
    else:
        run([FFMPEG,"-hide_banner","-loglevel","error","-ss",f"{pos:.3f}","-i",path,"-map","0:a:0","-t","0.25","-f","null","-"])

def duration(path):
    return float(out([FFPROBE,"-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",path]))

def packet_hash(path,seconds=5.0):
    p=run([FFMPEG,"-hide_banner","-loglevel","error","-i",path,"-map","0:a:0","-t",str(seconds),"-c:a","copy","-f","data","-"],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    return hashlib.sha256(p.stdout).hexdigest()

data=json.loads(SIDE.read_text(errors="replace"))
project=data["project"]
media=[Path(x) for x in project.get("media",[]) if Path(x).is_file()]
audio=[Path(x) for x in project.get("audio",[]) if Path(x).is_file()]
assert media,"real fixture has no media"
assert len(audio)>=15,f"real fixture requires 15 audio tracks, got {len(audio)}"

# Keep 7 physical media entries even when the source fixture has fewer unique images.
media7=(media*7)[:7]
track_durations=[duration(x) for x in audio]
first_two=audio[:2]
first_two_max=max(track_durations[:2])

def make_job(case_id,name,media_paths,audio_paths,hours,out_dir):
    return {
      "project":{
        "id":case_id,
        "name":name,
        "path":str(SIDE.parent),
        "media":[str(x) for x in media_paths],
        "audio":[str(x) for x in audio_paths],
        "valid":True,
        "error":None
      },
      "settings":{
        "width":1920,
        "height":1080,
        "fps":60,
        "codec":"h265",
        "bitrateMbps":4.0,
        "durationHours":hours,
        "durationMode":"whole-track",
        "loopMode":"loop",
        "crossfadeSec":0.0,
        "normalizeLufs":False,
        "outputDir":str(out_dir),
        "preset":"fast",
        "encoderPreference":"auto"
      },
      "effects":[],
      "subscribes":[],
      "ambient":None
    }

with tempfile.TemporaryDirectory(prefix="endlume865-render-job-e2e-") as td:
    root=Path(td)
    out_dir=root/"outputs";out_dir.mkdir()
    fixture=root/"jobs.json"
    result=root/"result.json"

    jobs=[
      make_job("e865-a-cold","E865 A cold",media[:1],first_two,2.0,out_dir),
      make_job("e865-d-warm","E865 D warm",media[:1],first_two,2.0,out_dir),
      make_job("e865-b-15tracks","E865 B 15 tracks",media[:1],audio[:15],2.0,out_dir),
      make_job("e865-c-7images","E865 C 7 images",media7,audio[:15],2.0,out_dir),
      make_job("e865-f-1h","E865 F 1 hour",media[:1],first_two,1.0,out_dir),
      make_job("e865-e-3h","E865 E 3 hours",media[:1],first_two,3.0,out_dir),
    ]
    fixture.write_text(json.dumps({"jobs":jobs},ensure_ascii=False,indent=2))

    env=os.environ.copy()
    env["ENDLUME_E2E_RENDER_JOB"]=str(fixture)
    env["ENDLUME_E2E_RESULT"]=str(result)
    env["RUST_BACKTRACE"]="1"
    started=time.perf_counter()
    proc=subprocess.run([str(APP)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=240)
    app_wall=time.perf_counter()-started
    if proc.returncode!=0:
        print(proc.stdout)
        print(proc.stderr,file=sys.stderr)
        raise SystemExit(f"ENDLUME app E2E exited {proc.returncode}")
    assert result.is_file(),"ENDLUME E2E result file missing"
    raw=json.loads(result.read_text(errors="replace"))
    assert raw.get("status")=="passed",raw
    rows=raw.get("results") or []
    assert len(rows)==len(jobs),(len(rows),len(jobs))

    verified=[]
    first_input_hash=packet_hash(first_two[0],5.0)
    for idx,(row,job) in enumerate(zip(rows,jobs)):
        assert row.get("status")=="passed",row
        output_path=Path(row["outputPath"])
        assert output_path.is_file(),output_path
        size=output_path.stat().st_size
        assert size>1_000_000,size
        assert int(row.get("outputBytes") or 0)==size,(row.get("outputBytes"),size)
        terminal=row.get("terminal") or {}
        assert terminal.get("resultPath")==str(output_path),(terminal.get("resultPath"),output_path)
        assert int(terminal.get("resultBytes") or 0)==size,(terminal.get("resultBytes"),size)
        assert terminal.get("status")=="done" and float(terminal.get("progress",0))==100.0,terminal

        probe=ffprobe_json(output_path)
        fd=float(probe["format"]["duration"])
        video=next(x for x in probe["streams"] if x.get("codec_type")=="video")
        aud=next(x for x in probe["streams"] if x.get("codec_type")=="audio")
        assert video.get("codec_name")=="hevc",video
        assert video.get("width")==1920 and video.get("height")==1080,video
        assert video.get("avg_frame_rate")=="60/1",video
        assert aud.get("codec_name")=="mp3",aud
        assert row.get("audioMode")=="ORIGINAL_MP3_PACKET_COPY",row

        target=job["settings"]["durationHours"]*3600.0
        max_track=max(duration(Path(x)) for x in job["project"]["audio"])
        assert fd>=target-1.0,(fd,target)
        assert fd<=target+max_track+2.0,(fd,target,max_track)

        for pos in (0.0,fd*.5,max(0.0,fd-10.0),max(0.0,fd-2.0)):
            seek(output_path,pos,"video");seek(output_path,pos,"audio")
        boundary=duration(Path(job["project"]["audio"][0]))
        seek(output_path,max(0.0,boundary-.2),"audio")
        seek(output_path,min(fd-.1,boundary+.2),"audio")

        # First MP3 packet payload must survive the final container stream-copy path.
        if idx in (0,1,4,5):
            assert packet_hash(output_path,5.0)==first_input_hash,"Original MP3 packet payload changed"

        wall=float(row.get("wallSeconds") or 0)
        verified.append({
          "id":row.get("id"),
          "wall_seconds":round(wall,3),
          "output_bytes":size,
          "duration_seconds":round(fd,3),
          "encoder":row.get("encoder"),
          "fast_path":row.get("fastPath"),
          "fast_path_reason":row.get("fastPathReason"),
          "codec":"hevc",
          "fps":"60/1",
          "audio":"mp3",
          "result_path_exists":True,
          "terminal_result_bytes_ok":True,
          "track_boundary_checked":True,
          "tail_checked":True
        })

    # The physical 8.64 user baseline was 46.0 s for the one-image/2-MP3 2h case.
    cold=verified[0]["wall_seconds"]
    warm=verified[1]["wall_seconds"]
    assert cold < 46.0,(cold,"must materially beat 8.64 physical baseline")
    assert warm < 46.0,(warm,"must materially beat 8.64 physical baseline")
    limit=float(os.environ.get("ENDLUME_865_REAL_E2E_MAX_SECONDS","15"))
    assert cold<=limit,(cold,limit)
    assert warm<=limit,(warm,limit)

    # Physical open/reveal command smoke on macOS. Uses the same OS commands as system.rs.
    open_video=False;reveal_folder=False
    if sys.platform=="darwin":
        first=Path(rows[0]["outputPath"])
        run(["/usr/bin/open","-g",first]);open_video=True
        run(["/usr/bin/open","-R",first]);reveal_folder=True

    metrics={
      "status":"passed",
      "release_gate":True,
      "kind":"REAL_ENDLUME_RENDER_JOB_E2E_865",
      "app_wall_seconds":round(app_wall,3),
      "baseline_864_seconds":46.0,
      "max_one_image_2h_seconds":limit,
      "open_video_smoke":open_video,
      "reveal_folder_smoke":reveal_folder,
      "results":verified
    }
    METRICS.write_text(json.dumps(metrics,ensure_ascii=False,indent=2))
    print("REAL_ENDLUME_RENDER_JOB_E2E_865_GREEN",json.dumps(metrics,ensure_ascii=False))
