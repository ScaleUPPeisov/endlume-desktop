#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ENDLUME_BUILD_CACHE_ROOT:-$HOME/.endlume-build-cache}"
KEEP="${ENDLUME_BUILD_CACHE_KEEP:-2}"
PROTECT="${CARGO_TARGET_DIR:-}"
MAX_BYTES="${ENDLUME_BUILD_CACHE_MAX_BYTES:-18000000000}"

mkdir -p "$ROOT"

python3 - "$ROOT" "$KEEP" "$PROTECT" "$MAX_BYTES" <<'PY'
import os, shutil, sys, time
from pathlib import Path

root=Path(sys.argv[1]).expanduser()
keep=max(1,int(sys.argv[2]))
protect=Path(sys.argv[3]).expanduser().resolve() if sys.argv[3].strip() else None
max_bytes=max(1,int(sys.argv[4]))

def size(p:Path)->int:
    total=0
    if not p.exists():
        return 0
    for base,dirs,files in os.walk(p):
        for n in files:
            q=Path(base)/n
            try: total+=q.stat().st_size
            except OSError: pass
    return total

def mtime(p:Path)->float:
    try: return p.stat().st_mtime
    except OSError: return 0.0

def is_protected(p:Path)->bool:
    if protect is None:
        return False
    try: return p.resolve()==protect
    except OSError: return False

before=size(root)
print(f"ENDLUME_BUILD_CACHE_BEFORE_BYTES={before}",flush=True)

# target-* is the expensive Rust/Tauri build cache. Keep current target plus the
# newest previous target only. Older targets are disposable build products.
targets=[p for p in root.iterdir() if p.is_dir() and p.name.startswith("target-")]
targets.sort(key=mtime,reverse=True)
protected=[p for p in targets if is_protected(p)]
normal=[p for p in targets if not is_protected(p)]
survivors=[]
for p in protected:
    if p not in survivors: survivors.append(p)
for p in normal:
    if len(survivors)>=keep: break
    survivors.append(p)

for p in targets:
    if p in survivors: continue
    b=size(p)
    print(f"ENDLUME_BUILD_CACHE_REMOVE={p} bytes={b}",flush=True)
    shutil.rmtree(p,ignore_errors=True)

# Sidecar downloads/extracts are recreated cheaply. Keep only two newest roots
# and remove stale archives/extract directories inside the survivors.
sidecars=[p for p in root.iterdir() if p.is_dir() and ("sidecar" in p.name.lower() or p.name.startswith("release-"))]
sidecars.sort(key=mtime,reverse=True)
for p in sidecars[keep:]:
    b=size(p);print(f"ENDLUME_BUILD_CACHE_REMOVE={p} bytes={b}",flush=True);shutil.rmtree(p,ignore_errors=True)
for p in sidecars[:keep]:
    for q in p.iterdir():
        if q.name=="extract" or q.suffix.lower() in {".zip",".tmp",".part"}:
            if q.is_dir(): shutil.rmtree(q,ignore_errors=True)
            else:
                try:q.unlink()
                except OSError:pass

# If two full targets still exceed the hard budget, keep the newest target as
# reusable compiler cache and compact the older survivor to release artifacts.
survivors=[p for p in survivors if p.exists()]
total=size(root)
if total>max_bytes and len(survivors)>1:
    newest=max(survivors,key=mtime)
    for p in sorted((x for x in survivors if x!=newest),key=mtime):
        bundle=p/"release"/"bundle"
        archive=root/f"kept-bundle-{p.name}-{int(time.time())}"
        if bundle.exists():
            archive.mkdir(parents=True,exist_ok=True)
            for child in bundle.iterdir():
                dst=archive/child.name
                try:
                    if child.is_dir(): shutil.copytree(child,dst,dirs_exist_ok=True)
                    else: shutil.copy2(child,dst)
                except OSError: pass
        b=size(p)
        print(f"ENDLUME_BUILD_CACHE_COMPACT={p} bytes={b}",flush=True)
        shutil.rmtree(p,ignore_errors=True)
        total=size(root)
        if total<=max_bytes: break

# Keep only two archived bundle snapshots as well.
archives=sorted([p for p in root.iterdir() if p.is_dir() and p.name.startswith("kept-bundle-")],key=mtime,reverse=True)
for p in archives[keep:]:
    shutil.rmtree(p,ignore_errors=True)

after=size(root)
print(f"ENDLUME_BUILD_CACHE_AFTER_BYTES={after}",flush=True)
print(f"ENDLUME_BUILD_CACHE_RECLAIMED_BYTES={max(0,before-after)}",flush=True)
print(f"ENDLUME_BUILD_CACHE_KEEP={keep}",flush=True)
print(f"ENDLUME_BUILD_CACHE_HARD_LIMIT_BYTES={max_bytes}",flush=True)
PY
