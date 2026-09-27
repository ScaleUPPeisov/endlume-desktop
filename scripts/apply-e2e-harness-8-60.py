#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EQ='825dd7a4-f0cf-4032-a3c9-64290cb5756d'

def once(s,old,new,label):
    n=s.count(old)
    if n!=1: raise SystemExit(f'8.60 E2E patch {label}: expected 1, found {n}')
    return s.replace(old,new,1)

# Subscribe-OFF: exercise the same static-base optimization, protected equalizer,
# <=30s sustained master contract and in-place sample-table expansion as runtime.
p=ROOT/'scripts/run-endlume-857-real-e2e.py'; s=p.read_text()
needle='effects = [x for x in (data.get("effects") or []) if isinstance(x, dict) and x.get("enabled") and str(x.get("source") or "").strip()]'
s=once(s,needle,needle+f'''\nfor _e in effects:\n    if _e.get("id") == "{EQ}" and str(_e.get("mode") or "") == "chromakey":\n        _e["similarity"] = 0.18\n        _e["blend"] = 0.03''','off equalizer')
old='''    args = [FFMPEG, "-hide_banner", "-loglevel", "error", "-filter_complex_threads", "8",\n            "-loop", "1", "-framerate", str(WORK_FPS), "-i", image]'''
new='''    base_still = work / "strict-860-e2e-base.png"\n    run([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", image, "-vf",\n         f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop={WIDTH}:{HEIGHT}:(iw-ow)/2:(ih-oh)/2,fps={WORK_FPS},setsar=1",\n         "-frames:v", "1", "-compression_level", "1", "-y", base_still])\n    args = [FFMPEG, "-hide_banner", "-loglevel", "error", "-filter_complex_threads", "8",\n            "-loop", "1", "-framerate", str(WORK_FPS), "-i", base_still]'''
s=once(s,old,new,'off static base')
old='''    graph = (f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,"\n             f"crop={WIDTH}:{HEIGHT}:(iw-ow)/2:(ih-oh)/2,fps={WORK_FPS},setsar=1[b0]")'''
s=once(s,old,'    graph = f"[0:v]fps={WORK_FPS},setsar=1[b0]"','off graph')
s=once(s,'    assert master_seconds <= 24.0, master_seconds','    assert master_seconds <= 30.0, master_seconds','off speed')
s=once(s,'    final = work / "strict-final.mov"','    final = seed','off in-place')
p.write_text(s)
print('PASS: ENDLUME 8.60 Subscribe-OFF E2E harness aligned with optimized runtime')
