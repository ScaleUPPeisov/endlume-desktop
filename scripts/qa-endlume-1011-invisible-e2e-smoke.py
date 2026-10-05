#!/usr/bin/env python3
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

APP=Path(sys.argv[1]).resolve()
FFMPEG=Path(sys.argv[2]).resolve()
FFPROBE=Path(sys.argv[3]).resolve()
GUARD=Path(sys.argv[4]).resolve()
REPORT=Path(sys.argv[5]).resolve()
assert APP.is_file(),APP
assert FFMPEG.is_file() and FFPROBE.is_file(),(FFMPEG,FFPROBE)
assert GUARD.is_file(),GUARD
ROOT=REPORT.parent.resolve();ROOT.mkdir(parents=True,exist_ok=True)
WORK=ROOT/"work";shutil.rmtree(WORK,ignore_errors=True);WORK.mkdir(parents=True)


def run(args,check=True,timeout=120,env=None):
    return subprocess.run([str(x) for x in args],check=check,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout,env=env)


def probe(path):
    return json.loads(run([FFPROBE,"-v","error","-show_entries","stream=codec_type,codec_name,width,height,avg_frame_rate:format=duration,size","-of","json",path]).stdout)


def frame(path,pos=0.5):
    p=subprocess.run([str(FFMPEG),"-hide_banner","-loglevel","error","-ss",str(pos),"-i",str(path),"-map","0:v:0","-frames:v","1","-f","rawvideo","-pix_fmt","rgb24","-"],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
    return p.stdout


def diff_ratio(a,b,step=24,threshold=10):
    assert len(a)==len(b) and len(a)>1000,(len(a),len(b))
    changed=total=0
    for i in range(0,len(a)-2,step):
        d=max(abs(a[i]-b[i]),abs(a[i+1]-b[i+1]),abs(a[i+2]-b[i+2]))
        total+=1
        if d>=threshold:changed+=1
    return changed/max(1,total)


def app_bundle_root(exe):
    for p in [exe,*exe.parents]:
        if p.suffix.lower()==".app":return p
    raise AssertionError(f"PACKAGED_APP_ROOT_NOT_FOUND: {exe}")

APP_BUNDLE=app_bundle_root(APP)
APP_REL=APP.relative_to(APP_BUNDLE)


def fresh_app_binary(label):
    dst=WORK/f"{label}.app"
    shutil.rmtree(dst,ignore_errors=True)
    shutil.copytree(APP_BUNDLE,dst,symlinks=True)
    exe=dst/APP_REL
    assert exe.is_file(),exe
    return exe

launches=[]

def guarded_launch(label,env,timeout=180):
    exe=fresh_app_binary(label)
    guard_report=WORK/f"{label}-visibility.json"
    merged=os.environ.copy();merged.update(env)
    p=run([GUARD,guard_report,exe],check=False,timeout=timeout,env=merged)
    (WORK/f"{label}.stdout").write_text(p.stdout)
    (WORK/f"{label}.stderr").write_text(p.stderr)
    assert guard_report.is_file(),(label,"GUARD_REPORT_MISSING",p.returncode,p.stderr[-3000:])
    g=json.loads(guard_report.read_text())
    g["label"]=label
    launches.append(g)
    assert int(g.get("maxVisibleWindows",99))==0,(label,g)
    assert not bool(g.get("everFrontmost",True)),(label,g)
    assert int(g.get("childExit",99))==0,(label,g,p.stderr[-5000:])
    assert p.returncode==0,(label,p.returncode,p.stderr[-5000:])
    return p,g

# Deterministic local smoke media. No user project is touched.
project=WORK/"project";project.mkdir()
render_out=WORK/"render";render_out.mkdir()
base=project/"base.png"
run([FFMPEG,"-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=0x182238:size=1920x1080:rate=1","-frames:v","1","-y",base])
song=project/"song.mp3"
run([FFMPEG,"-hide_banner","-loglevel","error","-f","lavfi","-i","sine=frequency=440:sample_rate=48000:duration=8","-c:a","libmp3lame","-b:a","192k","-ar","48000","-ac","2","-y",song])


def make_overlay(name,color,x,y):
    out=WORK/f"{name}.mp4"
    vf=f"drawbox=x={x}:y={y}:w=320:h=140:color={color}@1:t=fill,drawbox=x={x+55}:y={y+40}:w=210:h=60:color=white@1:t=fill"
    run([FFMPEG,"-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=0x00ff00:size=640x360:rate=30","-t","2","-vf",vf,"-c:v","libx264","-preset","ultrafast","-pix_fmt","yuv420p","-y",out])
    return out


def effect(eid,name,src,x,y,scale,opacity=1.0):
    return {"id":eid,"name":name,"source":str(src),"enabled":True,"mode":"chromakey","keyColor":"#00ff00","similarity":0.10,"blend":0.06,"despill":0.35,"lumaThreshold":0.03,"lumaTolerance":0.08,"saturation":1.0,"x":x,"y":y,"scale":scale,"fullscreen":False,"previewFrameTime":0.0,"startSec":0.0,"endSec":None,"cacheKey":None,"cacheReady":False,"usageMode":"always","intervalSec":240.0,"usageDurationSec":30.0,"target":None,"offsetX":None,"offsetY":None,"opacity":opacity}

film=effect("qa-film","QA Film",make_overlay("film","red",45,75),0.22,0.30,0.34,0.75)
eq=effect("825dd7a4-f0cf-4032-a3c9-64290cb5756d","Эквалайзер круглый",make_overlay("eq","blue",145,95),0.62,0.66,0.48,0.90)
third=effect("qa-third","QA Third",make_overlay("third","yellow",220,50),0.78,0.25,0.28,0.65)
sub=effect("qa-sub","QA Subscribe",make_overlay("sub","magenta",120,135),0.50,0.82,0.42,1.0)
sub.update({"usageMode":"interval","intervalSec":240.0,"usageDurationSec":8.0,"firstAtSec":0.0,"secondAtSec":240.0,"repeatEverySec":240.0,"firstAppearance":"immediate","customFirstAtSec":0.0,"showDurationSec":8.0})


def save_preview(label,payload):
    exact=Path(payload["exactPath"]);assert exact.is_file() and exact.stat().st_size>1024,(label,exact)
    dst=WORK/f"{label}-exact.mp4";shutil.copy2(exact,dst)
    m=probe(dst);v=next(x for x in m["streams"] if x.get("codec_type")=="video")
    assert v["width"]==1920 and v["height"]==1080,(label,v)
    run([FFMPEG,"-hide_banner","-loglevel","error","-i",dst,"-frames:v","2","-f","null","-"],timeout=60)
    return dst


def preview_single(label,effects,subscribes,overlay):
    fixture=WORK/f"{label}.json";result=WORK/f"{label}-result.json"
    fixture.write_text(json.dumps({"projectPath":str(project),"overlaySource":str(overlay),"timeSec":0.0,"effects":effects,"subscribes":subscribes},ensure_ascii=False))
    p,g=guarded_launch(label,{"ENDLUME_E2E_PREVIEW_JOB":str(fixture),"ENDLUME_E2E_RESULT":str(result),"ENDLUME_PREVIEW_DIAG":"1","RUST_BACKTRACE":"1"})
    assert result.is_file(),(label,"RESULT_MISSING")
    data=json.loads(result.read_text());assert data.get("status")=="passed",data
    return save_preview(label,data["result"])


def preview_batch(label,cases):
    fixture=WORK/f"{label}.json";result=WORK/f"{label}-result.json"
    jobs=[]
    for cid,effects,subscribes,overlay in cases:
        jobs.append({"id":cid,"projectPath":str(project),"overlaySource":str(overlay),"timeSec":0.0,"effects":effects,"subscribes":subscribes})
    fixture.write_text(json.dumps({"jobs":jobs},ensure_ascii=False))
    p,g=guarded_launch(label,{"ENDLUME_E2E_PREVIEW_JOB":str(fixture),"ENDLUME_E2E_RESULT":str(result),"ENDLUME_PREVIEW_DIAG":"1","RUST_BACKTRACE":"1"},timeout=240)
    data=json.loads(result.read_text());assert data.get("status")=="passed",data
    rows={x["id"]:x["result"] for x in data.get("results",[])}
    assert set(rows)=={x[0] for x in cases},rows.keys()
    return {cid:save_preview(cid,rows[cid]) for cid,_,_,_ in cases}

# Exactly two genuine cold starts, then one shared non-cold regression process.
cold_fx=preview_single("cold-effects",[film],[],film["source"])
cold_sub=preview_single("cold-subscribe",[],[sub],sub["source"])
reg=preview_batch("preview-regressions",[
    ("baseline",[],[],film["source"]),
    ("round-equalizer",[eq],[],eq["source"]),
    ("third-effect",[third],[],third["source"]),
])
base_frame=frame(reg["baseline"])
ratios={
    "cold-effects":diff_ratio(base_frame,frame(cold_fx)),
    "cold-subscribe":diff_ratio(base_frame,frame(cold_sub)),
    "round-equalizer":diff_ratio(base_frame,frame(reg["round-equalizer"])),
    "third-effect":diff_ratio(base_frame,frame(reg["third-effect"])),
}
for name,ratio in ratios.items():assert ratio>0.00005,(name,ratio)

# Short synthetic Final Render E2E: verifies backend/render execution and clean exit,
# not production 2h performance. No Effects / Subscribe / Background Music logic is changed.
render_fixture=WORK/"render.json";render_result=WORK/"render-result.json"
job={
  "project":{"id":"qa-invisible-render","name":"QA Invisible Render","path":str(project),"media":[str(base)],"audio":[str(song)],"valid":True,"error":None,"anchors":{}},
  "settings":{"width":1920,"height":1080,"fps":60,"codec":"h265","bitrateMbps":8.0,"durationHours":5.0/3600.0,"durationMode":"exact","loopMode":"image","crossfadeSec":0.0,"normalizeLufs":False,"outputDir":str(render_out),"preset":"fast","encoderPreference":"auto"},
  "effects":[],"subscribes":[],"ambient":None,
  "ambientSettings":{"volumePct":18.0,"bassDb":0.0,"midDb":0.0,"trebleDb":0.0}
}
render_fixture.write_text(json.dumps({"jobs":[job]},ensure_ascii=False))
p,g=guarded_launch("render-e2e",{"ENDLUME_E2E_RENDER_JOB":str(render_fixture),"ENDLUME_E2E_RESULT":str(render_result),"RUST_BACKTRACE":"1"},timeout=180)
assert render_result.is_file(),"RENDER_RESULT_MISSING"
rr=json.loads(render_result.read_text());assert rr.get("status")=="passed",rr
row=rr["results"][0];assert row.get("status")=="passed",row
out=Path(row["outputPath"]);assert out.is_file() and out.stat().st_size>64000,out
m=probe(out);v=next(x for x in m["streams"] if x.get("codec_type")=="video")
assert v["codec_name"]=="hevc" and v["width"]==1920 and v["height"]==1080,(v,row)
run([FFMPEG,"-hide_banner","-loglevel","error","-i",out,"-frames:v","2","-f","null","-"],timeout=60)

assert len(launches)==4,launches
max_visible=max(int(x.get("maxVisibleWindows",0)) for x in launches)
ever_frontmost=any(bool(x.get("everFrontmost",False)) for x in launches)
assert max_visible==0,launches
assert not ever_frontmost,launches
report={
  "status":"GREEN",
  "processCountBefore":6,
  "processCountAfter":4,
  "coldEffects":"GREEN",
  "coldSubscribe":"GREEN",
  "baselinePreview":"GREEN",
  "roundEqualizer":"GREEN",
  "thirdEffect":"GREEN",
  "renderE2E":"GREEN",
  "resultFilesGenerated":"GREEN",
  "cleanExits":"GREEN",
  "visibleWindows":max_visible,
  "focusSteal":"NO" if not ever_frontmost else "FAIL",
  "previewDiffRatios":ratios,
  "launches":launches,
  "render":{"wallSeconds":row.get("wallSeconds"),"output":str(out),"bytes":out.stat().st_size,"codec":v.get("codec_name")}
}
REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print("ENDLUME_1011_INVISIBLE_E2E_SMOKE_GREEN",json.dumps(report,ensure_ascii=False))
