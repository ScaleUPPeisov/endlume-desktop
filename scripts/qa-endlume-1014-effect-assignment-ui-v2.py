#!/usr/bin/env python3
from pathlib import Path

base=Path(__file__).with_name('qa-endlume-1014-effect-assignment-ui.py')
source=base.read_text(encoding='utf-8')
old='''def wait_ready(proc):
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
        osa(''' + "'''" + '''on run argv\\nset targetPid to (item 1 of argv) as integer\\ntell application "System Events"\\ntry\\nset p to first application process whose unix id is targetPid\\nset frontmost of p to true\\nkeystroke "q" using command down\\nend try\\nend tell\\nend run''' + "'''" + ''',proc.pid)
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
'''
new='''def process_alive(pid):
    try:
        os.kill(int(pid),0)
        return True
    except (ProcessLookupError,PermissionError,ValueError):
        return False

def resolve_real_app_pid(launcher,timeout=12):
    deadline=time.time()+timeout
    exact=str(EXE)
    while time.time()<deadline:
        rows=run(['/usr/bin/pgrep','-x',EXE_NAME],check=False).stdout.split()
        for raw in rows:
            try: pid=int(raw)
            except ValueError: continue
            cmd=run(['/bin/ps','-p',str(pid),'-o','command='],check=False).stdout.strip()
            if cmd.startswith(exact):
                return pid
        if launcher.poll() is None:
            cmd=run(['/bin/ps','-p',str(launcher.pid),'-o','command='],check=False).stdout.strip()
            if cmd.startswith(exact): return launcher.pid
        time.sleep(.15)
    raise AssertionError(f'REAL_TAURI_PROCESS_NOT_FOUND launcher_rc={launcher.poll()}')

class AppProc:
    def __init__(self,launcher,pid,out,err):
        self.launcher=launcher; self.pid=pid; self._qa_out=out; self._qa_err=err
    def poll(self):
        return None if process_alive(self.pid) else 0
    @property
    def returncode(self):
        return self.launcher.poll()

def wait_ready(proc):
    deadline=time.time()+40
    while time.time()<deadline:
        if not process_alive(proc.pid): raise AssertionError(f'APP_EXITED_EARLY real_pid={proc.pid} launcher_rc={proc.returncode}')
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
    launcher=subprocess.Popen([str(EXE)],env=ENV,stdout=out,stderr=err,text=True)
    pid=resolve_real_app_pid(launcher)
    proc=AppProc(launcher,pid,out,err)
    wait_ready(proc)
    return proc

def stop(proc,graceful=True):
    if process_alive(proc.pid) and graceful:
        osa(''' + "'''" + '''on run argv\\nset targetPid to (item 1 of argv) as integer\\ntell application "System Events"\\ntry\\nset p to first application process whose unix id is targetPid\\nset frontmost of p to true\\nkeystroke "q" using command down\\nend try\\nend tell\\nend run''' + "'''" + ''',proc.pid)
        deadline=time.time()+8
        while time.time()<deadline and process_alive(proc.pid): time.sleep(.1)
    if process_alive(proc.pid):
        kids=run(['/usr/bin/pgrep','-P',str(proc.pid)],check=False).stdout.split()
        for kid in kids:
            try: os.kill(int(kid),signal.SIGTERM)
            except Exception: pass
        try: os.kill(proc.pid,signal.SIGTERM)
        except Exception: pass
        deadline=time.time()+3
        while time.time()<deadline and process_alive(proc.pid): time.sleep(.1)
        if process_alive(proc.pid):
            try: os.kill(proc.pid,signal.SIGKILL)
            except Exception: pass
    if proc.launcher.poll() is None:
        try: proc.launcher.terminate()
        except Exception: pass
    proc._qa_out.close(); proc._qa_err.close()
'''
if source.count(old)!=1:
    raise SystemExit(f'Unexpected effect UI process harness shape: {source.count(old)}')
source=source.replace(old,new)
code=compile(source,str(base),'exec')
g={'__name__':'__main__','__file__':str(base),'__package__':None}
exec(code,g,g)
