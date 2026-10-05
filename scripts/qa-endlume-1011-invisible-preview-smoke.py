#!/usr/bin/env python3
import json, os, subprocess, sys, tempfile
from pathlib import Path

if len(sys.argv) != 6:
    raise SystemExit("usage: qa-endlume-1011-invisible-preview-smoke.py APP FFMPEG FFPROBE GUARD REPORT")

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
cut='\nsettings={"width":1920'
assert cut in source,"PREVIEW_ONLY_CUT_ANCHOR_NOT_FOUND"
source=source.split(cut,1)[0]

# This smoke is strictly Preview/window QA. Do not create the 15-minute
# background-music fixture from the full acceptance harness.
bg_start='\nbackground=tmp_root/"background-15m.m4a"\n'
bg_end='assert 895<=background_duration<=905,background_duration\n'
assert bg_start in source,"BACKGROUND_FIXTURE_START_NOT_FOUND"
bg_a=source.index(bg_start)
assert bg_end in source[bg_a:],"BACKGROUND_FIXTURE_END_NOT_FOUND"
bg_b=source.index(bg_end,bg_a)+len(bg_end)
source=source[:bg_a]+'\n'+source[bg_b:]

# Inject the visibility guard into the exact three packaged app launches used by
# the proven critical Preview acceptance: cold-effects, cold-subscribe and the
# shared baseline/round-equalizer/third-effect batch.
report_anchor='REPORT=Path(sys.argv[4]).resolve()'
assert report_anchor in source,"REPORT_ANCHOR_NOT_FOUND"
source=source.replace(report_anchor,report_anchor+'\nGUARD=Path(os.environ["ENDLUME_QA_VISIBILITY_GUARD"]).resolve()\nassert GUARD.is_file(),GUARD',1)

list_anchor='lib_path,lib=load_library()'
assert list_anchor in source,"VISIBILITY_LIST_ANCHOR_NOT_FOUND"
source=source.replace(list_anchor,'visibility_reports=[]\n'+list_anchor,1)

single_old='''    app_bin=fresh_app_binary(label)\n    p=run([app_bin],check=False,timeout=150,env=env)'''
single_new='''    app_bin=fresh_app_binary(label)\n    visibility_file=tmp_root/f"{label}-visibility.json"\n    p=run([GUARD,visibility_file,app_bin],check=False,timeout=150,env=env)\n    assert visibility_file.is_file(),(label,"VISIBILITY_REPORT_MISSING")\n    visibility=json.loads(visibility_file.read_text());visibility["label"]=label\n    visibility_reports.append(visibility)\n    assert int(visibility.get("childExit",99))==0,(label,visibility)\n    assert int(visibility.get("maxVisibleWindows",99))==0,(label,visibility)\n    assert visibility.get("everFrontmost") is False,(label,visibility)'''
assert single_old in source,"SINGLE_PREVIEW_GUARD_ANCHOR_NOT_FOUND"
source=source.replace(single_old,single_new,1)

batch_old='''    app_bin=fresh_app_binary(label)\n    p=run([app_bin],check=False,timeout=240,env=env)'''
batch_new='''    app_bin=fresh_app_binary(label)\n    visibility_file=tmp_root/f"{label}-visibility.json"\n    p=run([GUARD,visibility_file,app_bin],check=False,timeout=240,env=env)\n    assert visibility_file.is_file(),(label,"VISIBILITY_REPORT_MISSING")\n    visibility=json.loads(visibility_file.read_text());visibility["label"]=label\n    visibility_reports.append(visibility)\n    assert int(visibility.get("childExit",99))==0,(label,visibility)\n    assert int(visibility.get("maxVisibleWindows",99))==0,(label,visibility)\n    assert visibility.get("everFrontmost") is False,(label,visibility)'''
assert batch_old in source,"BATCH_PREVIEW_GUARD_ANCHOR_NOT_FOUND"
source=source.replace(batch_old,batch_new,1)

source += r'''

assert len(visibility_reports)==3,visibility_reports
labels=[x.get("label") for x in visibility_reports]
assert labels==["cold-effects","cold-subscribe","preview-regressions"],labels
max_visible=max(int(x.get("maxVisibleWindows",99)) for x in visibility_reports)
ever_frontmost=any(bool(x.get("everFrontmost",True)) for x in visibility_reports)
assert max_visible==0,visibility_reports
assert not ever_frontmost,visibility_reports
report={
  "status":"GREEN",
  "previewProcessCount":3,
  "combinedProcessCountBefore":6,
  "combinedProcessCountAfter":4,
  "coldEffects":"GREEN",
  "coldSubscribe":"GREEN",
  "baselinePreview":"GREEN",
  "roundEqualizer":"GREEN",
  "thirdEffect":"GREEN",
  "resultFilesGenerated":"GREEN",
  "cleanExits":"GREEN",
  "visibleWindows":0,
  "focusSteal":"NO",
  "previewDiffs":preview_diffs,
  "launches":visibility_reports,
}
REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print("PREVIEW_PROCESS_COUNT=3",flush=True)
print("COLD_EFFECTS=GREEN",flush=True)
print("COLD_SUBSCRIBE=GREEN",flush=True)
print("BASELINE_PREVIEW=GREEN",flush=True)
print("ROUND_EQUALIZER=GREEN",flush=True)
print("THIRD_EFFECT=GREEN",flush=True)
print("RESULT_FILES=GREEN",flush=True)
print("CLEAN_EXITS=GREEN",flush=True)
print("VISIBLE_WINDOWS=0",flush=True)
print("FOCUS_STEAL=NO",flush=True)
print("ENDLUME_1011_INVISIBLE_PREVIEW_SMOKE_GREEN",flush=True)
'''

with tempfile.TemporaryDirectory(prefix="endlume-preview-smoke-runner-") as td:
    runner=Path(td)/"critical-preview-only.py"
    runner.write_text(source)
    env=os.environ.copy()
    env["ENDLUME_QA_VISIBILITY_GUARD"]=str(GUARD)
    proc=subprocess.run(
        [sys.executable,str(runner),str(APP),str(FFMPEG),str(FFPROBE),str(REPORT)],
        cwd=Path.cwd(),env=env,text=True)
    raise SystemExit(proc.returncode)
