#!/usr/bin/env python3
from pathlib import Path
import json, os, subprocess, sys, tempfile

ROOT=Path(__file__).resolve().parents[1]
LIVE=(ROOT/"src-tauri/src/live_preview.rs").read_text(errors="replace")

required=[
  "validate_video_proxy",
  "FFprobe не подтвердил video stream / geometry / duration",
  "proxy не декодируется",
  "accept_proxy_attempt(process.is_ok(),validation.is_ok())",
  "libx264 fallback",
  "safe fps fallback",
  "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1",
  "scale=640:-2:flags=lanczos,fps=60",
]
for token in required:
    assert token in LIVE,token
assert "async fn encode_proxy(app:&AppHandle,prefix:Vec<String>,safe_prefix:Option<Vec<String>>,out:&Path)" in LIVE
assert LIVE.count("minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")==1
print("ENDLUME_866_LIVE_PREVIEW_SOURCE_CONTRACT_GREEN")

if "--physical" not in sys.argv:
    raise SystemExit(0)
idx=sys.argv.index("--physical")
FFMPEG=Path(sys.argv[idx+1]).resolve()
FFPROBE=Path(sys.argv[idx+2]).resolve()

def run(args,capture=False):
    return subprocess.run([str(x) for x in args],check=True,stdout=subprocess.PIPE if capture else None,stderr=subprocess.PIPE if capture else None,text=True)

def probe(path):
    p=run([FFPROBE,"-v","error","-select_streams","v:0","-show_entries","stream=codec_type,width,height:format=duration","-of","json",path],True)
    d=json.loads(p.stdout)
    s=(d.get("streams") or [{}])[0]
    assert s.get("codec_type")=="video",d
    assert int(s.get("width") or 0)>0 and int(s.get("height") or 0)>0,d
    assert float(d.get("format",{}).get("duration") or 0)>0,d
    run([FFMPEG,"-hide_banner","-loglevel","error","-ss","0","-i",path,"-map","0:v:0","-frames:v","1","-f","null","-"])
    return d

def encode(src,out,filter_expr,codec):
    args=[FFMPEG,"-hide_banner","-loglevel","error","-stream_loop","-1","-i",src,"-t","2","-an","-vf",filter_expr]
    if codec=="h264_videotoolbox":
        args += ["-c:v",codec,"-realtime","1","-q:v","72","-pix_fmt","yuv420p"]
    else:
        args += ["-c:v","libx264","-preset","ultrafast","-crf","18","-pix_fmt","yuv420p"]
    args += ["-movflags","+faststart","-y",out]
    run(args)

with tempfile.TemporaryDirectory(prefix="endlume866-preview-") as td:
    td=Path(td)
    effect=td/"effect.mp4"
    subscribe=td/"subscribe.mp4"
    run([FFMPEG,"-hide_banner","-loglevel","error","-f","lavfi","-i","testsrc2=size=1280x720:rate=30","-t","2","-vf","drawbox=x=80:y=80:w=360:h=180:color=lime@1:t=fill","-c:v","libx264","-pix_fmt","yuv420p","-y",effect])
    run([FFMPEG,"-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=0x00ff00:size=854x480:rate=30","-t","2","-vf","drawbox=x=240:y=160:w=360:h=120:color=red@1:t=fill","-c:v","libx264","-pix_fmt","yuv420p","-y",subscribe])

    primary_filter="scale=640:-2:flags=fast_bilinear,minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
    safe_filter="scale=640:-2:flags=lanczos,fps=60"
    rows=[]
    for name,src in [("effects",effect),("subscribe",subscribe)]:
        out=td/f"{name}-proxy.mp4"
        used="h264_videotoolbox"
        try:
            encode(src,out,primary_filter,used)
            probe(out)
        except Exception:
            if out.exists(): out.unlink()
            used="libx264"
            try:
                encode(src,out,primary_filter,used)
                probe(out)
            except Exception:
                if out.exists(): out.unlink()
                used="libx264-safe-fps"
                encode(src,out,safe_filter,"libx264")
                probe(out)
        rows.append({"kind":name,"encoder":used,"bytes":out.stat().st_size})
    assert all(r["bytes"]>1024 for r in rows),rows
    print("ENDLUME_866_LIVE_PREVIEW_PHYSICAL_GREEN",json.dumps(rows,ensure_ascii=False))
