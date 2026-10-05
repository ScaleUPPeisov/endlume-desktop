#!/usr/bin/env python3
import json, os, subprocess, sys, tempfile
from pathlib import Path

if len(sys.argv) != 6:
    raise SystemExit("usage: qa-endlume-1011-invisible-targeted-perf.py APP FFMPEG FFPROBE GUARD REPORT")

APP=Path(sys.argv[1]).resolve()
FFMPEG=Path(sys.argv[2]).resolve()
FFPROBE=Path(sys.argv[3]).resolve()
GUARD=Path(sys.argv[4]).resolve()
REPORT=Path(sys.argv[5]).resolve()
assert APP.is_file(),APP
assert FFMPEG.is_file() and FFPROBE.is_file(),(FFMPEG,FFPROBE)
assert GUARD.is_file(),GUARD
REPORT.parent.mkdir(parents=True,exist_ok=True)

source_path=Path(__file__).with_name("qa-endlume-1011-critical-hotfix.py")
source=source_path.read_text()

# No Preview and no 15-minute Background Music fixture in this diagnostic.
# We only measure the real Effects+Subscribe Final Render cold/warm pair.
bg_start='\nbackground=tmp_root/"background-15m.m4a"\n'
bg_end='assert 895<=background_duration<=905,background_duration\n'
assert bg_start in source and bg_end in source,"BACKGROUND_FIXTURE_ANCHOR_NOT_FOUND"
a=source.index(bg_start); b=source.index(bg_end,a)+len(bg_end)
source=source[:a]+'\n'+source[b:]

preview_start='# Cold tests remain truly fresh processes. Non-cold preview regressions share one E2E process.\n'
settings_anchor='settings={"width":1920'
assert preview_start in source and settings_anchor in source,"PREVIEW_STRIP_ANCHOR_NOT_FOUND"
a=source.index(preview_start); b=source.index(settings_anchor,a)
source=source[:a]+source[b:]

# Visibility guard is inherited by the real E2E child process.
report_anchor='REPORT=Path(sys.argv[4]).resolve()'
assert report_anchor in source,"REPORT_ANCHOR_NOT_FOUND"
source=source.replace(report_anchor,report_anchor+'\nGUARD=Path(os.environ["ENDLUME_QA_VISIBILITY_GUARD"]).resolve()\nassert GUARD.is_file(),GUARD',1)

jobs_start='jobs=[\n'
render_anchor='render_fixture=tmp_root/"render-jobs.json"'
assert jobs_start in source and render_anchor in source,"JOBS_ANCHOR_NOT_FOUND"
a=source.index(jobs_start,source.index('exact_202=')); b=source.index(render_anchor,a)
replacement='''jobs=[\n    job("e1011-perf-cold","ENDLUME 10.0.11 PERF EFFECTS COLD",[film,eq,third]),\n    job("e1011-perf-warm","ENDLUME 10.0.11 PERF EFFECTS WARM",[film,eq,third]),\n]\n'''
source=source[:a]+replacement+source[b:]

launch_old='''render_app=fresh_app_binary("render-e2e")\nstarted=time.perf_counter();rp=run([render_app],check=False,timeout=300,env=env);app_wall=time.perf_counter()-started'''
launch_new='''render_app=fresh_app_binary("render-e2e")\nvisibility_file=tmp_root/"render-visibility.json"\nstarted=time.perf_counter();rp=run([GUARD,visibility_file,render_app],check=False,timeout=180,env=env);app_wall=time.perf_counter()-started\nassert visibility_file.is_file(),"VISIBILITY_REPORT_MISSING"\nvisibility=json.loads(visibility_file.read_text())\nassert int(visibility.get("childExit",99))==0,visibility\nassert int(visibility.get("maxVisibleWindows",99))==0,visibility\nassert visibility.get("everFrontmost") is False,visibility'''
assert launch_old in source,"RENDER_LAUNCH_ANCHOR_NOT_FOUND"
source=source.replace(launch_old,launch_new,1)

# Replace the full acceptance tail with pure diagnostic collection. Do not fail
# merely because the performance target is missed; record exact timings first.
tail_anchor='render_meta={}\n'
assert tail_anchor in source,"TAIL_ANCHOR_NOT_FOUND"
a=source.index(tail_anchor,source.index('rows={x["id"]:x for x in raw["results"]}'))
source=source[:a]+r'''render_meta={}
timings={}
cache_events=[]
for line in rp.stderr.splitlines():
    if "ENDLUME_DIAG " not in line:continue
    try:d=json.loads(line.split("ENDLUME_DIAG ",1)[1].strip())
    except Exception:continue
    pid=str(d.get("projectId") or "")
    if d.get("kind")=="engine-timing" and pid:
        timings.setdefault(pid,{}).setdefault(str(d.get("key")),[]).append(float(d.get("seconds") or 0.0))
    elif d.get("kind")=="cache":cache_events.append(d)

for pid,row in rows.items():
    p=Path(row["outputPath"]);assert p.is_file(),p
    meta=probe(p)
    v=next(x for x in meta["streams"] if x.get("codec_type")=="video")
    astream=next(x for x in meta["streams"] if x.get("codec_type")=="audio")
    mib=p.stat().st_size/1048576
    duration=float(meta["format"]["duration"])
    assert v["codec_name"]=="hevc" and v["width"]==1920 and v["height"]==1080 and v["avg_frame_rate"]=="60/1",(pid,v)
    assert astream["codec_name"]=="aac" and int(astream["sample_rate"])==48000 and int(astream["channels"])==2,(pid,astream)
    assert 400<=mib<=600,(pid,mib)
    render_meta[pid]={
      "wall":float(row["wallSeconds"]),"mib":mib,"duration":duration,
      "fastPath":row.get("fastPath"),"fastPathReason":row.get("fastPathReason"),
      "encoder":row.get("encoder"),"videoCodec":v.get("codec_name"),"audioCodec":astream.get("codec_name")
    }

cold=render_meta["e1011-perf-cold"];warm=render_meta["e1011-perf-warm"]
perf_green=cold["wall"]<=20.0 and warm["wall"]<=20.0
report={
  "status":"GREEN","performanceGate":"GREEN" if perf_green else "RED",
  "visibleWindows":0,"focusSteal":"NO","cleanExit":"GREEN",
  "appWallSeconds":app_wall,"render":render_meta,"timings":timings,
  "cache":cache_events,"visibility":visibility,
  "project":str(project),"tracks":len(songs),
  "effects":{"film":film.get("name"),"equalizer":eq.get("name"),"third":third.get("name"),"subscribe":sub.get("name")},
}
REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print("TARGETED_PERF_COLD="+json.dumps(cold,ensure_ascii=False,sort_keys=True),flush=True)
print("TARGETED_PERF_WARM="+json.dumps(warm,ensure_ascii=False,sort_keys=True),flush=True)
print("TARGETED_TIMINGS_COLD="+json.dumps(timings.get("e1011-perf-cold",{}),ensure_ascii=False,sort_keys=True),flush=True)
print("TARGETED_TIMINGS_WARM="+json.dumps(timings.get("e1011-perf-warm",{}),ensure_ascii=False,sort_keys=True),flush=True)
print("TARGETED_CACHE="+json.dumps(cache_events,ensure_ascii=False,sort_keys=True),flush=True)
print("VISIBLE_WINDOWS=0",flush=True)
print("FOCUS_STEAL=NO",flush=True)
print("TARGETED_PERFORMANCE_GATE="+("GREEN" if perf_green else "RED"),flush=True)
print("ENDLUME_1011_INVISIBLE_TARGETED_PERF_DIAGNOSTIC_GREEN",flush=True)
for row in rows.values():
    try:Path(row["outputPath"]).unlink()
    except Exception:pass
'''

with tempfile.TemporaryDirectory(prefix="endlume-perf-runner-") as td:
    runner=Path(td)/"targeted-render-perf.py"
    runner.write_text(source)
    env=os.environ.copy()
    env["ENDLUME_QA_VISIBILITY_GUARD"]=str(GUARD)
    proc=subprocess.run(
        [sys.executable,str(runner),str(APP),str(FFMPEG),str(FFPROBE),str(REPORT)],
        cwd=Path.cwd(),env=env,text=True)
    raise SystemExit(proc.returncode)
