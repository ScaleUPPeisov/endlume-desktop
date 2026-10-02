#!/usr/bin/env python3
import json, os, re, subprocess, sys
from pathlib import Path

HOME=Path.home()
LIB=HOME/"Library/Application Support/studio.endlume.desktop/library.json"
print("DIAG_LIBRARY_PATH="+str(LIB))
if not LIB.is_file():
    print("DIAG_LIBRARY_MISSING=1")
    raise SystemExit(2)
data=json.loads(LIB.read_text())
subs=[x for x in data.get("subscribes",[]) if isinstance(x,dict)]
print("SUBSCRIBE_COUNT="+str(len(subs)))
for i,s in enumerate(subs):
    src=Path(str(s.get("source","")))
    interval=s.get("intervalSec",s.get("repeatEverySec",240))
    first=s.get("firstAppearance","<missing>")
    custom=s.get("customFirstAtSec")
    show=s.get("showDurationSec",s.get("usageDurationSec",8))
    print(f"SUB[{i}].NAME={s.get('name')}")
    print(f"SUB[{i}].ENABLED={s.get('enabled')}")
    print(f"SUB[{i}].USAGE_MODE={s.get('usageMode')}")
    print(f"SUB[{i}].SOURCE={src}")
    print(f"SUB[{i}].SOURCE_EXISTS={src.is_file()}")
    print(f"SUB[{i}].INTERVAL={interval}")
    print(f"SUB[{i}].FIRST_APPEARANCE={first}")
    print(f"SUB[{i}].CUSTOM_FIRST={custom}")
    print(f"SUB[{i}].SHOW_DURATION={show}")
    print(f"SUB[{i}].X={s.get('x')}")
    print(f"SUB[{i}].Y={s.get('y')}")
    print(f"SUB[{i}].SCALE={s.get('scale')}")
    print(f"SUB[{i}].OPACITY={s.get('opacity',1)}")
    print(f"SUB[{i}].MODE={s.get('mode')}")
    print(f"SUB[{i}].KEY_COLOR={s.get('keyColor')}")
    print(f"SUB[{i}].SIMILARITY={s.get('similarity')}")
    print(f"SUB[{i}].BLEND={s.get('blend')}")
    print(f"SUB[{i}].DESPILL={s.get('despill')}")

# Read persisted UI feature flag without mutating it.
needle=b"endlume-feature-flags-v2"
roots=[
    HOME/"Library/WebKit/studio.endlume.desktop",
    HOME/"Library/Application Support/studio.endlume.desktop",
    HOME/"Library/Containers/studio.endlume.desktop",
]
hits=[]
for root in roots:
    if not root.exists():
        continue
    for p in root.rglob("*"):
        try:
            if not p.is_file() or p.stat().st_size>20*1024*1024:
                continue
            raw=p.read_bytes()
            if needle in raw:
                hits.append((p,raw))
        except Exception:
            pass
print("FEATURE_FLAG_STORAGE_HITS="+str(len(hits)))
for p,raw in hits[:10]:
    pos=raw.find(needle)
    chunk=raw[max(0,pos-400):pos+1200]
    txt=chunk.decode("utf-8","replace").replace("\x00","")
    print("FEATURE_FLAG_FILE="+str(p))
    print("FEATURE_FLAG_CONTEXT="+repr(txt))

# Inspect latest final video around scheduled Subscribe moments.
out=Path("/Volumes/TOSHIBA EXT/ВАЙРОН/Render/Brewroom Jazz")
videos=[]
if out.is_dir():
    for p in out.glob("*.mp4"):
        try: videos.append((p.stat().st_mtime,p))
        except Exception: pass
videos.sort(reverse=True)
if videos:
    latest=videos[0][1]
    print("LATEST_FINAL="+str(latest))
    print("LATEST_FINAL_BYTES="+str(latest.stat().st_size))
else:
    print("LATEST_FINAL=<none>")
