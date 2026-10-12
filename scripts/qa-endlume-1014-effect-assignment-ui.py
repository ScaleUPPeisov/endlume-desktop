#!/usr/bin/env python3
import json, os, shutil, signal, subprocess, sys, tempfile, time, uuid
from pathlib import Path

APP=Path(sys.argv[1]).resolve()
FFMPEG=Path(sys.argv[2]).resolve()
REPORT=Path(sys.argv[3]).resolve()
VOL=Path('/Volumes/TOSHIBA EXT')
assert APP.is_dir() and (APP/'Contents/Info.plist').is_file(),APP
assert FFMPEG.is_file(),FFMPEG
assert VOL.is_dir(),'TOSHIBA EXT_NOT_MOUNTED'

REAL_HOME=Path.home()
QA=Path(tempfile.mkdtemp(prefix='endlume1014-effect-ui-'))
ISO_HOME=QA/'home'; ISO_HOME.mkdir(parents=True)
APPDATA=ISO_HOME/'Library/Application Support/studio.endlume.desktop'
INBOX=APPDATA/'VYRON Inbox'; INBOX.mkdir(parents=True)
ROOT=VOL/'ВАЙРОН'/'ENDLUME-QA-10.0.14-EFFECT-UI'
BATCH=ROOT/'Batch'; OUT=VOL/'ВАЙРОН'/'Render'/'ENDLUME QA 10.0.14 Effects UI'
BATCH.mkdir(parents=True,exist_ok=True); OUT.mkdir(parents=True,exist_ok=True)

EXE_NAME=subprocess.check_output(['/usr/bin/plutil','-extract','CFBundleExecutable','raw','-o','-',str(APP/'Contents/Info.plist')],text=True).strip()
EXE=APP/'Contents/MacOS'/EXE_NAME
assert EXE.is_file() and os.access(EXE,os.X_OK),EXE

def run(args,**kw):
    return subprocess.run([str(x) for x in args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,**kw)

def load_real_library():
    candidates=[REAL_HOME/'Library/Application Support/studio.endlume.desktop/library.json']
    for base in [REAL_HOME/'Library/Application Support',REAL_HOME/'Library/Containers']:
        if not base.exists(): continue
        try:
            candidates += list(base.rglob('library.json'))
        except Exception: pass
    seen=set()
    for p in candidates:
        try:
            p=p.resolve()
            if p in seen or not p.is_file() or p.stat().st_size>20_000_000: continue
            seen.add(p); d=json.loads(p.read_text(encoding='utf-8'))
        except Exception: continue
        effects=[x for x in d.get('effects',[]) if isinstance(x,dict)]
        round_fx=next((x for x in effects if x.get('id')=='825dd7a4-f0cf-4032-a3c9-64290cb5756d' or 'qa round equalizer' in str(x.get('name','')).lower() or 'эквалайзер круглый' in str(x.get('name','')).lower()),None)
        if not round_fx: continue
        def ready(x):
            return x.get('enabled') is True and str(x.get('usageMode','always'))!='off' and Path(str(x.get('source',''))).is_file()
        if not ready(round_fx): continue
        other=next((x for x in effects if x.get('id')!=round_fx.get('id') and ready(x)),None)
        if other: return p,d,round_fx,other
    raise AssertionError('REAL_LIBRARY_WITH_ROUND_EQUALIZER_AND_SECOND_EFFECT_NOT_FOUND')

LIB_PATH,LIB,ROUND,OTHER=load_real_library()
ROUND_ID=str(ROUND['id']); ROUND_NAME=str(ROUND.get('name') or 'QA Round Equalizer')
OTHER_ID=str(OTHER['id']); OTHER_NAME=str(OTHER.get('name') or OTHER_ID)

# 20 real, valid project folders on the external drive. One shared source is copied
# to every folder so the scanner sees ordinary physical files, not a mock project.
template=ROOT/'template'; template.mkdir(parents=True,exist_ok=True)
cover=template/'обложка QA 1014.png'; audio=template/'музыка QA 1014.mp3'
if not cover.is_file():
    p=run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x172033:s=1920x1080','-frames:v','1','-y',cover],timeout=90); assert p.returncode==0,p.stderr
if not audio.is_file():
    p=run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=523:sample_rate=48000:duration=30','-c:a','libmp3lame','-b:a','320k','-ar','48000','-ac','2','-y',audio],timeout=90); assert p.returncode==0,p.stderr

projects=[]
for i in range(1,21):
    d=BATCH/f'{i:03d} QA Effect Project'; d.mkdir(parents=True,exist_ok=True)
    dst_cover=d/'cover.png'; dst_audio=d/'track.mp3'
    for src,dst in [(cover,dst_cover),(audio,dst_audio)]:
        if dst.exists(): dst.unlink()
        try: os.link(src,dst)
        except OSError: shutil.copy2(src,dst)
    projects.append({'projectId':f'qa-effect-{i:03d}','folderPath':str(d),'tracks':[{'path':str(dst_audio)}]})

batch_id='ENDLUME-QA-EFFECT-1014'
manifest=BATCH/'batch.json'; status=BATCH/'status.json'
manifest.write_text(json.dumps({
  'source':'VYRON Production Manager QA 10.0.14','batchId':batch_id,'channelId':'qa-effects-1014','channelName':'ENDLUME QA Effects 10.0.14',
  'rootPath':str(BATCH),'outputDir':str(OUT),'statusPath':str(status),'projectCount':20,'projects':projects
},ensure_ascii=False,indent=2),encoding='utf-8')
status.write_text(json.dumps({'batchId':batch_id,'projects':[{'projectId':p['projectId'],'renderStatus':'Queued'} for p in projects]},ensure_ascii=False,indent=2),encoding='utf-8')

ENV=os.environ.copy(); ENV['HOME']=str(ISO_HOME); ENV['ENDLUME_E2E_LIBRARY_PATH']=str(LIB_PATH); ENV['RUST_BACKTRACE']='1'

def make_request(label):
    INBOX.mkdir(parents=True,exist_ok=True)
    req=INBOX/f'{label}-{uuid.uuid4().hex}.json'
    req.write_text(json.dumps({'batchId':batch_id,'manifestPath':str(manifest),'requestedAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'selectedProjectIds':[p['projectId'] for p in projects],'schemaVersion':1},ensure_ascii=False,indent=2),encoding='utf-8')
    return req

def osa(script,*args,timeout=20):
    p=run(['/usr/bin/osascript','-',*map(str,args)],input=script,timeout=timeout)
    return p.returncode,(p.stdout or '').strip(),(p.stderr or '').strip()

PRESS='''
on run argv
  set targetPid to (item 1 of argv) as integer
  set needle to item 2 of argv
  tell application "System Events"
    try
      set p to first application process whose unix id is targetPid
      set frontmost of p to true
      repeat with w in windows of p
        repeat with e in entire contents of w
          set nm to ""
          set ds to ""
          set vl to ""
          try
            set nm to name of e as text
          end try
          try
            set ds to description of e as text
          end try
          try
            set vl to value of e as text
          end try
          set blob to nm & " " & ds & " " & vl
          if blob contains needle then
            try
              perform action "AXPress" of e
              return "CLICKED:" & blob
            end try
          end if
        end repeat
      end repeat
    on error errText
      return "ERROR:" & errText
    end try
  end tell
  return "NOT_FOUND"
end run
'''

CONTAINS='''
on run argv
  set targetPid to (item 1 of argv) as integer
  set needle to item 2 of argv
  tell application "System Events"
    try
      set p to first application process whose unix id is targetPid
      repeat with w in windows of p
        repeat with e in entire contents of w
          set nm to ""
          set ds to ""
          set vl to ""
          try
            set nm to name of e as text
          end try
          try
            set ds to description of e as text
          end try
          try
            set vl to value of e as text
          end try
          if (nm & " " & ds & " " & vl) contains needle then return "YES"
        end repeat
      end repeat
    end try
  end tell
  return "NO"
end run
'''

DUMP='''
on run argv
  set targetPid to (item 1 of argv) as integer
  set out to ""
  tell application "System Events"
    try
      set p to first application process whose unix id is targetPid
      repeat with w in windows of p
        repeat with e in entire contents of w
          set nm to ""
          set ds to ""
          try
            set nm to name of e as text
          end try
          try
            set ds to description of e as text
          end try
          if nm is not "" or ds is not "" then set out to out & nm & " | " & ds & linefeed
        end repeat
      end repeat
    end try
  end tell
  return out
end run
'''

RETURN_KEY='''
on run argv
 set targetPid to (item 1 of argv) as integer
 tell application "System Events"
  try
   set p to first application process whose unix id is targetPid
   set frontmost of p to true
   key code 36
  end try
 end tell
 return "OK"
end run
'''

def click(pid,needle,timeout=25):
    deadline=time.time()+timeout; last=''
    while time.time()<deadline:
        rc,out,err=osa(PRESS,pid,needle); last=out or err
        if out.startswith('CLICKED:'): return out
        osa(RETURN_KEY,pid)
        time.sleep(.45)
    raise AssertionError(f'UI_CLICK_FAILED needle={needle!r} last={last!r}')

def visible(pid,needle):
    rc,out,err=osa(CONTAINS,pid,needle); return out=='YES'

def wait_ready(proc):
    deadline=time.time()+40
    while time.time()<deadline:
        if proc.poll() is not None: raise AssertionError(f'APP_EXITED_EARLY rc={proc.returncode}')
        # dismiss the VYRON imported-info dialog if it is blocking the WebView
        osa(RETURN_KEY,proc.pid)
        if visible(proc.pid,'Применить ко всем найденным проектам') and visible(proc.pid,ROUND_NAME) and visible(proc.pid,'020 QA Effect Project'):
            return
        time.sleep(.7)
    rc,dump,err=osa(DUMP,proc.pid,timeout=30); (QA/'ui-timeout.txt').write_text(dump or err,encoding='utf-8')
    raise AssertionError('PROJECT_PAGE_WITH_20_EFFECT_ROWS_NOT_READY')

def launch(label):
    make_request(label)
    out=open(QA/f'{label}.stdout','w'); err=open(QA/f'{label}.stderr','w')
    proc=subprocess.Popen([str(EXE)],env=ENV,stdout=out,stderr=err,text=True)
    proc._qa_out=out; proc._qa_err=err
    wait_ready(proc)
    return proc

def stop(proc,graceful=True):
    if proc.poll() is None and graceful:
        osa('''on run argv\nset targetPid to (item 1 of argv) as integer\ntell application "System Events"\ntry\nset p to first application process whose unix id is targetPid\nset frontmost of p to true\nkeystroke "q" using command down\nend try\nend tell\nend run''',proc.pid)
        try: proc.wait(timeout=8)
        except subprocess.TimeoutExpired: pass
    if proc.poll() is None:
        kids=run(['/usr/bin/pgrep','-P',str(proc.pid)],check=False).stdout.split()
        for kid in kids:
            try: os.kill(int(kid),signal.SIGTERM)
            except Exception: pass
        try: proc.terminate(); proc.wait(timeout=5)
        except Exception:
            try: proc.kill()
            except Exception: pass
    proc._qa_out.close(); proc._qa_err.close()

def clear_runtime_state():
    for name in ['queue.json','recovery.json','session.json']:
        try: (APPDATA/name).unlink()
        except FileNotFoundError: pass

def queue_selection(expected_id,timeout=8):
    q=APPDATA/'queue.json'; deadline=time.time()+timeout; best=[]
    while time.time()<deadline:
        try:
            d=json.loads(q.read_text(encoding='utf-8')); jobs=[]
            if isinstance(d.get('active'),dict): jobs.append(d['active'])
            jobs.extend(x for x in (d.get('pending') or []) if isinstance(x,dict))
            if len(jobs)>=20:
                ids=[str((x.get('project') or {}).get('selectedEffectId','')) for x in jobs[:20]]
                assert len(ids)==20 and all(x==expected_id for x in ids),(expected_id,ids)
                return {'count':len(jobs),'selectedIds':ids,'outputDirs':sorted(set(str((x.get('settings') or {}).get('outputDir','')) for x in jobs))}
            best=jobs
        except Exception: pass
        time.sleep(.12)
    raise AssertionError(f'QUEUE_20_NOT_OBSERVED expected={expected_id} observed={len(best)}')

results={'roundName':ROUND_NAME,'roundId':ROUND_ID,'otherName':OTHER_NAME,'otherId':OTHER_ID,'libraryPath':str(LIB_PATH),'isolatedHome':str(ISO_HOME),'projectCount':20}

# 1) Real Project page: select Round, switch to another real effect, select Round again.
p=launch('select-round')
try:
    results['roundClick1']=click(p.pid,ROUND_NAME)
    results['otherClickBeforeRestart']=click(p.pid,OTHER_NAME)
    results['roundClickFinal']=click(p.pid,ROUND_NAME)
    rc,dump,err=osa(DUMP,p.pid,timeout=30); (QA/'ui-select-round.txt').write_text(dump or err,encoding='utf-8')
finally: stop(p,graceful=True)

# 2) Reopen same isolated profile + same 20 project paths. DO NOT select again.
# Enqueue immediately: all queue jobs must still carry Round Equalizer ID.
clear_runtime_state(); p=launch('restart-persist')
try:
    results['restartHadRoundVisible']=visible(p.pid,ROUND_NAME)
    results['enqueueAfterRestart']=click(p.pid,'ДОБАВИТЬ В ОЧЕРЕДЬ')
    results['persistedRoundQueue']=queue_selection(ROUND_ID)
finally: stop(p,graceful=False); clear_runtime_state()

# 3) Re-import, switch all 20 to a second real preset, enqueue and prove IDs changed.
p=launch('switch-other')
try:
    results['otherClick']=click(p.pid,OTHER_NAME)
    results['enqueueOther']=click(p.pid,'ДОБАВИТЬ В ОЧЕРЕДЬ')
    results['otherQueue']=queue_selection(OTHER_ID)
finally: stop(p,graceful=False); clear_runtime_state()

# 4) Re-import, explicitly disable assignment with product's canonical "Без эффекта",
# enqueue and prove every job snapshot contains __none__.
p=launch('disable-effect')
try:
    results['noneClick']=click(p.pid,'БЕЗ ЭФФЕКТА')
    results['enqueueNone']=click(p.pid,'ДОБАВИТЬ В ОЧЕРЕДЬ')
    results['noneQueue']=queue_selection('__none__')
finally: stop(p,graceful=False); clear_runtime_state()

results['status']='GREEN'
results['assignmentPersistedAcrossRestart']=True
results['all20QueuedWithRound']=True
results['switchToAnotherEffect']=True
results['disableAssignment']=True
REPORT.parent.mkdir(parents=True,exist_ok=True); REPORT.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('EFFECT_UI_20_PROJECTS=GREEN')
print('EFFECT_SELECT_ROUND=GREEN')
print('EFFECT_RESTART_PERSISTENCE=GREEN')
print('EFFECT_SWITCH_OTHER=GREEN')
print('EFFECT_DISABLE_NONE=GREEN')
print('EFFECT_QUEUE_SNAPSHOT_20=GREEN')
