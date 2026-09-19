#!/usr/bin/env python3
import hashlib, json, os, shutil, struct, subprocess, sys, tempfile, time
from pathlib import Path

ROOT=Path(os.environ.get("GITHUB_WORKSPACE") or Path(__file__).resolve().parents[1]).resolve()
SIDE=Path(sys.argv[1]).resolve()
FFMPEG=Path(sys.argv[2]).resolve()
FFPROBE=Path(sys.argv[3]).resolve()
METRICS=Path(sys.argv[4] if len(sys.argv)>4 else "863-fast-multistill.json").resolve()
WIDTH,HEIGHT,FPS=1920,1080,60
MEDIA_COUNT=7
PHYSICAL_FRAMES=30
LOGICAL_FRAMES=600

def log(*x): print("[e863-multi]",*x,flush=True)
def run(args,*,capture=False,env=None,cwd=None):
    p=subprocess.run([str(x) for x in args],check=True,stdout=subprocess.PIPE if capture else None,stderr=subprocess.PIPE if capture else None,env=env,cwd=cwd)
    return p
def out(args): return run(args,capture=True).stdout.decode(errors="replace").strip()
def duration(p): return float(out([FFPROBE,"-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",p]))
def stream_json(p):
    return json.loads(out([FFPROBE,"-v","error","-show_entries","stream=index,codec_type,codec_name,pix_fmt,width,height,avg_frame_rate,nb_frames,sample_rate,channels,bit_rate","-of","json",p]))["streams"]
def count_frames(p): return int(out([FFPROBE,"-v","error","-select_streams","v:0","-count_frames","-show_entries","stream=nb_read_frames","-of","default=nw=1:nk=1",p]))
def packet_hash(p,seconds=None):
    a=[FFMPEG,"-hide_banner","-loglevel","error","-i",p,"-map","0:a:0"]
    if seconds is not None:a+=["-t",f"{seconds:.6f}"]
    a+=["-c:a","copy","-f","data","-"]
    return hashlib.sha256(run(a,capture=True).stdout).hexdigest()
def audio_sig(p):
    x=out([FFPROBE,"-v","error","-select_streams","a:0","-show_entries","stream=codec_name,sample_rate,channels","-of","csv=p=0:s=|",p]).split("|")
    return x[0],int(x[1]),int(x[2])
def seek(p,pos,kind):
    if kind=="video":run([FFMPEG,"-hide_banner","-loglevel","error","-ss",f"{pos:.3f}","-i",p,"-map","0:v:0","-frames:v","2","-f","null","-"])
    else:run([FFMPEG,"-hide_banner","-loglevel","error","-ss",f"{pos:.3f}","-i",p,"-map","0:a:0","-t","0.25","-f","null","-"])
def unique_packet_bytes(p,stream):
    proc=subprocess.Popen([str(FFPROBE),"-v","error","-select_streams",stream,"-show_entries","packet=pos,size","-of","csv=p=0",str(p)],stdout=subprocess.PIPE,text=True)
    seen=set();logical=0;unique=0;count=0
    assert proc.stdout is not None
    for line in proc.stdout:
        parts=[x.strip() for x in line.strip().split(",")]
        if len(parts)<2: continue
        try: pos=int(parts[0]); size=int(parts[1])
        except ValueError:
            try: size=int(parts[0]);pos=int(parts[1])
            except Exception: continue
        logical+=size;count+=1
        key=(pos,size)
        if key not in seen:seen.add(key);unique+=size
    rc=proc.wait()
    if rc: raise RuntimeError(f"ffprobe packets failed {stream}: {rc}")
    return {"packets":count,"logical_bytes":logical,"unique_payload_bytes":unique,"unique_packet_locations":len(seen)}
def top_atoms(p):
    total=p.stat().st_size; atoms=[];off=0
    with p.open("rb") as f:
        while off+8<=total:
            f.seek(off);h=f.read(16)
            if len(h)<8:break
            size=struct.unpack(">I",h[:4])[0];typ=h[4:8].decode("latin1")
            hdr=8
            if size==1:
                if len(h)<16:break
                size=struct.unpack(">Q",h[8:16])[0];hdr=16
            elif size==0:size=total-off
            if size<hdr or off+size>total:break
            atoms.append({"type":typ,"offset":off,"bytes":size});off+=size
    return atoms
def make_whole_duration(track_durations,target):
    total=0.0;i=0
    while total<target:
        total+=max(.1,track_durations[i%len(track_durations)]);i+=1
        if i>10000:raise RuntimeError("whole-track runaway")
    return total,i

data=json.loads(SIDE.read_text(errors="replace"))
project=data["project"];settings=data.get("settings") or {}
source=Path(project["media"][0]);audios=[Path(x) for x in project["audio"]]
assert source.is_file();assert len(audios)==15 and all(x.is_file() for x in audios)
sigs=[audio_sig(x) for x in audios];assert all(x[0]=="mp3" for x in sigs),sigs;assert all(x==sigs[0] for x in sigs),sigs
track_durations=[duration(x) for x in audios]
target=7200.0
final_duration,track_instances=make_whole_duration(track_durations,target)
total_frames=max(MEDIA_COUNT*LOGICAL_FRAMES,int(round(final_duration*FPS)))

# Compile the exact Rust manifest harness before performance timing.
run(["cargo","test","--manifest-path","src-tauri/Cargo.toml","external_multistill_manifest_if_requested","--","--nocapture"],cwd=ROOT)

results=[]
last_detail=None
with tempfile.TemporaryDirectory(prefix="endlume863-multi-") as td:
    root=Path(td)
    media=[]
    for i in range(MEDIA_COUNT):
        dst=root/f"still-{i+1:02}{source.suffix.lower() or '.png'}";shutil.copy2(source,dst);media.append(dst)

    # Fidelity proof is outside wall timing.
    original_hashes=[packet_hash(x) for x in audios]

    for iteration in range(1,6):
        work=root/f"run-{iteration}";work.mkdir()
        render_start=time.perf_counter()
        clips=[]
        for i,img in enumerate(media):
            clip=work/f"physical-{i:02}.mp4"
            vf=f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop={WIDTH}:{HEIGHT}:(iw-ow)/2:(ih-oh)/2,fps={FPS},setsar=1,format=yuv420p"
            run([FFMPEG,"-hide_banner","-loglevel","error","-loop","1","-framerate",str(FPS),"-i",img,"-vf",vf,"-frames:v",str(PHYSICAL_FRAMES),"-an",
                 "-c:v","hevc_videotoolbox","-realtime","1","-prio_speed","0","-power_efficient","0","-q:v","100","-b:v","500k","-maxrate","12M","-bufsize","64M","-g","120","-tag:v","hvc1","-pix_fmt","yuv420p",
                 "-fps_mode","cfr","-r",str(FPS),"-video_track_timescale","60000","-y",clip])
            assert count_frames(clip)==PHYSICAL_FRAMES
            clips.append(clip)

        vlist=work/"video-list.txt";vlist.write_text("\n".join(f"file '{p.as_posix()}'" for p in clips)+"\n")
        pool=work/"physical-pool.mp4"
        run([FFMPEG,"-hide_banner","-loglevel","error","-f","concat","-safe","0","-i",vlist,"-an","-c:v","copy","-y",pool])
        assert count_frames(pool)==MEDIA_COUNT*PHYSICAL_FRAMES

        clean=[]
        for i,src in enumerate(audios,1):
            dst=work/f"audio-{i:02}.mp3"
            run([FFMPEG,"-hide_banner","-loglevel","error","-i",src,"-map","0:a:0","-c:a","copy","-map_metadata","-1","-write_xing","0","-id3v2_version","0","-y",dst])
            clean.append(dst)
        raw=work/"audio-list.txt";raw.write_text("\n".join(str(x) for x in clean)+"\n")
        cycle=work/"audio-cycle.mp3"
        run([FFMPEG,"-hide_banner","-loglevel","error","-fflags","+genpts","-i",f"concatf:{raw}","-map","0:a:0","-c:a","copy","-map_metadata","-1","-write_xing","0","-id3v2_version","0","-y",cycle])

        seed=work/"seed.mov"
        run([FFMPEG,"-hide_banner","-loglevel","error","-i",pool,"-stream_loop","-1","-fflags","+genpts","-i",cycle,"-t",f"{final_duration:.9f}",
             "-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-y",seed])
        assert packet_hash(cycle,5.0)==packet_hash(seed,5.0)

        final=work/"final.mov"
        env=os.environ.copy();env.update({
            "ENDLUME_MULTI_MANIFEST_SEED":str(seed),
            "ENDLUME_MULTI_MANIFEST_OUT":str(final),
            "ENDLUME_MULTI_MEDIA_COUNT":str(MEDIA_COUNT),
            "ENDLUME_MULTI_PHYSICAL_FRAMES":str(PHYSICAL_FRAMES),
            "ENDLUME_MULTI_LOGICAL_FRAMES":str(LOGICAL_FRAMES),
            "ENDLUME_MULTI_TOTAL_FRAMES":str(total_frames),
        })
        run(["cargo","test","--manifest-path","src-tauri/Cargo.toml","external_multistill_manifest_if_requested","--","--nocapture"],env=env,cwd=ROOT)
        wall=time.perf_counter()-render_start

        size=final.stat().st_size;assert 0<size<=700_000_000,size
        streams=stream_json(final);video=next(x for x in streams if x.get("codec_type")=="video");audio=next(x for x in streams if x.get("codec_type")=="audio")
        fd=duration(final)
        assert video.get("codec_name")=="hevc",video
        assert video.get("width")==WIDTH and video.get("height")==HEIGHT,video
        assert video.get("avg_frame_rate")=="60/1",video
        assert audio.get("codec_name")=="mp3",audio
        assert int(audio.get("sample_rate"))==sigs[0][1] and int(audio.get("channels"))==sigs[0][2],audio
        assert abs(fd-final_duration)<=1.0,(fd,final_duration)
        assert packet_hash(cycle,5.0)==packet_hash(final,5.0)
        for pos in (0.0,fd*.5,max(0.0,fd-2.0)):
            seek(final,pos,"video");seek(final,pos,"audio")
        assert wall<=30.0,wall

        record={"run":iteration,"wall_seconds":round(wall,3),"final_bytes":size,"final_duration":round(fd,6),"encoder":"hevc_videotoolbox"}
        results.append(record);log("RUN",json.dumps(record))
        if iteration==5:
            vp=unique_packet_bytes(final,"v:0");ap=unique_packet_bytes(final,"a:0");atoms=top_atoms(final)
            moov=sum(x["bytes"] for x in atoms if x["type"]=="moov");mdat=sum(x["bytes"] for x in atoms if x["type"]=="mdat")
            overhead=size-vp["unique_payload_bytes"]-ap["unique_payload_bytes"]
            last_detail={
                "container_total_bytes":size,
                "video_payload_bytes":vp["unique_payload_bytes"],
                "video_logical_packet_bytes":vp["logical_bytes"],
                "audio_payload_bytes":ap["unique_payload_bytes"],
                "audio_logical_packet_bytes":ap["logical_bytes"],
                "moov_bytes":moov,
                "mdat_bytes":mdat,
                "container_overhead_bytes":overhead,
                "other_atoms_bytes":size-moov-mdat,
                "video_packets":vp["packets"],
                "audio_packets":ap["packets"],
                "physical_master_bytes":pool.stat().st_size,
                "audio_cycle_bytes":cycle.stat().st_size,
                "atoms":atoms,
            }

# Source MP3 packets survive clean remux individually.
with tempfile.TemporaryDirectory(prefix="endlume863-audio-proof-") as td:
    proof=Path(td)
    for i,src in enumerate(audios):
        dst=proof/f"{i:02}.mp3";run([FFMPEG,"-hide_banner","-loglevel","error","-i",src,"-map","0:a:0","-c:a","copy","-map_metadata","-1","-write_xing","0","-id3v2_version","0","-y",dst])
        assert packet_hash(src)==original_hashes[i]==packet_hash(dst)

assert results[-1]["wall_seconds"] <= max(30.0,results[0]["wall_seconds"]*1.25)
metrics={
    "status":"passed","release_gate":True,"fast_path":"FAST_MULTI_STILL","media_count":MEDIA_COUNT,
    "audio_count":len(audios),"whole_track":True,"crossfade_sec":0.0,"normalize_lufs":False,
    "target_seconds":target,"final_video_duration_seconds":round(final_duration,6),
    "width":WIDTH,"height":HEIGHT,"fps":"60/1","video_codec":"hevc","audio_codec":"mp3",
    "mp3_packet_copy":True,"synthetic_padding":False,"seek_begin":True,"seek_middle":True,"seek_tail":True,
    "runs":results,"breakdown":last_detail,
}
METRICS.write_text(json.dumps(metrics,ensure_ascii=False,indent=2))
log("PASS",json.dumps(metrics,ensure_ascii=False))
