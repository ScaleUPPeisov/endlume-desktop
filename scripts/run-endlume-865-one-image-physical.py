#!/usr/bin/env python3
import json, os, subprocess, sys, tempfile, time
from pathlib import Path

ROOT=Path(os.environ.get("GITHUB_WORKSPACE") or Path(__file__).resolve().parents[1]).resolve()
SIDE=Path(sys.argv[1]).resolve()
FFMPEG=Path(sys.argv[2]).resolve()
FFPROBE=Path(sys.argv[3]).resolve()
METRICS=Path(sys.argv[4] if len(sys.argv)>4 else "865-one-image-physical.json").resolve()
WIDTH,HEIGHT,FPS=1920,1080,60
PHYSICAL_FRAMES=30
LOGICAL_FRAMES=600

def encoder_works(name):
    try:
        run([FFMPEG,"-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=black:s=640x360:r=60","-frames:v","30","-an","-c:v",name,"-pix_fmt","yuv420p","-f","null","-"])
        return True
    except Exception:
        return False

def choose_encoder():
    if len(sys.argv)>5 and sys.argv[5].strip():
        name=sys.argv[5].strip()
        if not encoder_works(name): raise RuntimeError(f"requested encoder unavailable: {name}")
        return name
    for name in (["hevc_videotoolbox","libx265"] if sys.platform=="darwin" else ["hevc_nvenc","hevc_qsv","hevc_amf","libx265"]):
        if encoder_works(name): return name
    raise RuntimeError("no HEVC encoder available")

def encoder_args(name):
    if name=="hevc_videotoolbox":
        return ["-c:v",name,"-realtime","1","-prio_speed","0","-power_efficient","0","-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M","-g","120","-tag:v","hvc1","-pix_fmt","yuv420p"]
    if name=="hevc_nvenc":
        return ["-c:v",name,"-preset","p4","-rc","vbr","-cq","18","-b:v","500k","-maxrate","12M","-bufsize","64M","-g","120","-tag:v","hvc1","-pix_fmt","yuv420p"]
    if name=="hevc_qsv":
        return ["-c:v",name,"-global_quality","18","-maxrate","12M","-bufsize","64M","-g","120","-tag:v","hvc1","-pix_fmt","nv12"]
    if name=="hevc_amf":
        return ["-c:v",name,"-quality","balanced","-rc","vbr_peak","-b:v","500k","-maxrate","12M","-g","120","-tag:v","hvc1","-pix_fmt","yuv420p"]
    return ["-c:v","libx265","-preset","ultrafast","-crf","18","-maxrate","500k","-bufsize","4M","-x265-params","keyint=120:min-keyint=120:scenecut=0:open-gop=0:aq-mode=3:aq-strength=1.0:vbv-init=1.0","-tag:v","hvc1","-pix_fmt","yuv420p"]

def run(args,*,capture=False,env=None,cwd=None):
    return subprocess.run([str(x) for x in args],check=True,stdout=subprocess.PIPE if capture else None,stderr=subprocess.PIPE if capture else None,env=env,cwd=cwd)

def out(args):
    return run(args,capture=True).stdout.decode(errors="replace").strip()

def duration(p):
    return float(out([FFPROBE,"-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",p]))

def sig(p):
    v=out([FFPROBE,"-v","error","-select_streams","a:0","-show_entries","stream=codec_name,sample_rate,channels","-of","csv=p=0:s=|",p]).split("|")
    return v[0],int(v[1]),int(v[2])

def seek(p,pos,kind):
    if kind=="video":
        run([FFMPEG,"-hide_banner","-loglevel","error","-ss",f"{pos:.3f}","-i",p,"-map","0:v:0","-frames:v","2","-f","null","-"])
    else:
        run([FFMPEG,"-hide_banner","-loglevel","error","-ss",f"{pos:.3f}","-i",p,"-map","0:a:0","-t","0.25","-f","null","-"])

def whole_duration(ds,target=7200.0):
    total=0.0;i=0
    while total<target:
        total+=max(.1,ds[i%len(ds)]);i+=1
        if i>10000: raise RuntimeError("whole-track runaway")
    return total,i

def ffconcat_escape(p):
    s=str(p).replace("\\","/")
    out=[]
    for c in s:
        if c in " '#": out.append("\\")
        out.append(c)
    return "".join(out)

data=json.loads(SIDE.read_text(errors="replace"))
project=data["project"]
image=Path(project["media"][0])
audios=[Path(x) for x in project["audio"][:2]]
assert image.is_file(),image
assert len(audios)==2 and all(x.is_file() for x in audios),audios
sigs=[sig(x) for x in audios]
assert all(x[0]=="mp3" for x in sigs),sigs
assert sigs[0]==sigs[1],sigs
durations=[duration(x) for x in audios]
final_duration,instances=whole_duration(durations)
total_frames=max(PHYSICAL_FRAMES,int(round(final_duration*FPS)))
ENCODER=choose_encoder()
print("ENDLUME_865_ENCODER",ENCODER,flush=True)

# Compile the exact sample-table implementation before performance timing.
run(["cargo","test","--manifest-path","src-tauri/Cargo.toml","external_multistill_manifest_if_requested","--no-run"],cwd=ROOT)

records=[]
with tempfile.TemporaryDirectory(prefix="endlume865-one-") as td:
    root=Path(td)
    for idx in range(2):
        work=root/f"run-{idx+1}";work.mkdir()
        started=time.perf_counter()

        master=work/"fast-865-still.mp4"
        vf=f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop={WIDTH}:{HEIGHT}:(iw-ow)/2:(ih-oh)/2,fps={FPS},setsar=1"
        t0=time.perf_counter()
        run([FFMPEG,"-hide_banner","-loglevel","error","-loop","1","-framerate","60","-i",image,
             "-vf",vf,"-frames:v",str(PHYSICAL_FRAMES),"-an",
             *encoder_args(ENCODER),
             "-fps_mode","cfr","-r","60","-video_track_timescale","60000","-y",master])
        visual=time.perf_counter()-t0

        alist=work/"audio-direct-list.txt"
        alist.write_text("\n".join(f"file {ffconcat_escape(x)}" for x in audios)+"\n")
        probe=work/"audio-direct-probe.mp3"
        t0=time.perf_counter()
        run([FFMPEG,"-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",alist,
             "-t","12","-map","0:a:0","-c:a","copy","-map_metadata","-1","-write_xing","0","-id3v2_version","0","-y",probe])
        run([FFMPEG,"-hide_banner","-loglevel","error","-i",probe,"-map","0:a:0","-t","1","-f","null","-"])
        audio_prepare=time.perf_counter()-t0

        seed=work/"seed.mp4"
        t0=time.perf_counter()
        run([FFMPEG,"-hide_banner","-loglevel","error","-i",master,
             "-stream_loop","-1","-f","concat","-safe","0","-fflags","+genpts","-i",alist,
             "-t",f"{final_duration:.9f}","-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-y",seed])
        audio_mux=time.perf_counter()-t0

        final=work/"final.mp4"
        env=os.environ.copy()
        env.update({
          "ENDLUME_MULTI_MANIFEST_SEED":str(seed),
          "ENDLUME_MULTI_MANIFEST_OUT":str(final),
          "ENDLUME_MULTI_MEDIA_COUNT":"1",
          "ENDLUME_MULTI_PHYSICAL_FRAMES":str(PHYSICAL_FRAMES),
          "ENDLUME_MULTI_LOGICAL_FRAMES":str(LOGICAL_FRAMES),
          "ENDLUME_MULTI_TOTAL_FRAMES":str(total_frames),
        })
        t0=time.perf_counter()
        run(["cargo","test","--manifest-path","src-tauri/Cargo.toml","external_multistill_manifest_if_requested","--","--nocapture"],env=env,cwd=ROOT)
        manifest=time.perf_counter()-t0

        t0=time.perf_counter()
        probe_json=json.loads(out([FFPROBE,"-v","error","-show_entries","stream=codec_type,codec_name,pix_fmt,width,height,avg_frame_rate,sample_rate,channels:format=duration","-of","json",final]))
        fd=float(probe_json["format"]["duration"])
        video=next(x for x in probe_json["streams"] if x.get("codec_type")=="video")
        audio=next(x for x in probe_json["streams"] if x.get("codec_type")=="audio")
        assert video.get("codec_name")=="hevc",video
        assert video.get("width")==WIDTH and video.get("height")==HEIGHT,video
        assert video.get("avg_frame_rate")=="60/1",video
        assert audio.get("codec_name")=="mp3",audio
        assert int(audio.get("sample_rate"))==sigs[0][1] and int(audio.get("channels"))==sigs[0][2],audio
        assert abs(fd-final_duration)<=1.0,(fd,final_duration)
        for pos in (0.0,fd*.5,max(0.0,fd-10.0),max(0.0,fd-2.0)):
            seek(final,pos,"video");seek(final,pos,"audio")
        boundary=durations[0]
        seek(final,max(0.0,boundary-.2),"audio");seek(final,min(fd-.1,boundary+.2),"audio")
        validation=time.perf_counter()-t0

        wall=time.perf_counter()-started
        size=final.stat().st_size
        assert size>1_000_000,size
        # Physical 8.64 user baseline was 46 s. 8.65 must materially beat it.
        assert wall<=15.0,wall
        records.append({
          "run":idx+1,"cold":idx==0,"wall_seconds":round(wall,3),"visual_master_seconds":round(visual,3),
          "audio_prepare_seconds":round(audio_prepare,3),"audio_mux_seconds":round(audio_mux,3),
          "manifest_seconds":round(manifest,3),"validation_seconds":round(validation,3),
          "output_bytes":size,"duration":round(fd,6),"codec":"hevc","fps":"60/1","audio":"mp3","encoder":ENCODER,
          "track_boundary_checked":True
        })
        print("ENDLUME_865_ONE_IMAGE_RUN",json.dumps(records[-1]),flush=True)

metrics={"status":"passed","release_gate":True,"baseline_864_seconds":46.0,"project":"1 image + 2 MP3 + 2h whole-track","runs":records}
METRICS.write_text(json.dumps(metrics,ensure_ascii=False,indent=2))
print("ENDLUME_865_ONE_IMAGE_PHYSICAL_GREEN",json.dumps(metrics,ensure_ascii=False),flush=True)
