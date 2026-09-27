#!/usr/bin/env python3
import json,os,shutil,statistics,sys,tempfile,time
from pathlib import Path

volume=Path(sys.argv[1]).resolve()
out=Path(sys.argv[2]).resolve()
assert volume.is_dir(), volume
local_root=Path.home()/'.endlume-ci-fixtures'/'e861-local-scratch'
local_root.mkdir(parents=True,exist_ok=True)
src=local_root/'final-500000000.bin'
size=500_000_000
if not src.is_file() or src.stat().st_size!=size:
    tmp=src.with_suffix('.tmp')
    with tmp.open('wb',buffering=0) as f:
        chunk=b'\x5a'*(8*1024*1024)
        left=size
        while left:
            b=chunk if left>=len(chunk) else chunk[:left]
            f.write(b); left-=len(b)
        f.flush(); os.fsync(f.fileno())
    tmp.replace(src)

target_dir=volume/'.ENDLUME-861-CI'
target_dir.mkdir(parents=True,exist_ok=True)
times=[]
for i in range(1,6):
    dst=target_dir/f'final-{i}.mov'
    part=target_dir/f'.final-{i}.endlume-part'
    for p in (dst,part): p.unlink(missing_ok=True)
    t=time.perf_counter()
    with src.open('rb',buffering=0) as fi, part.open('wb',buffering=0) as fo:
        shutil.copyfileobj(fi,fo,length=8*1024*1024)
        fo.flush(); os.fsync(fo.fileno())
    part.replace(dst)
    dt=time.perf_counter()-t
    assert dst.stat().st_size==size
    times.append(dt)
    print('EXTERNAL_FINAL',json.dumps({'iteration':i,'seconds':round(dt,3),'bytes':size}),flush=True)
    dst.unlink(missing_ok=True)
    time.sleep(1)
try: target_dir.rmdir()
except OSError: pass
ratio=max(times)/max(min(times),0.001)
doc={'status':'passed','bytes':size,'times':[round(x,3) for x in times],'median':round(statistics.median(times),3),'max':round(max(times),3),'ratio':round(ratio,3),'slope':round(times[-1]-times[0],3)}
# The purpose is stability, not a synthetic SSD benchmark. Allow a wide absolute
# ceiling, but reject the runaway 3x+ degradation seen in production projects.
assert ratio<2.0,doc
assert max(times)<20.0,doc
out.write_text(json.dumps(doc,ensure_ascii=False,indent=2))
print(json.dumps(doc,ensure_ascii=False,indent=2))
