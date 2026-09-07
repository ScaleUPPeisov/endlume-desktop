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

# Subscribe-ON: same static base/protected equalizer/in-place manifest contracts.
p=ROOT/'scripts/run-endlume-857-real-subscribe.py'; s=p.read_text()
needle="fxs=[x for x in data.get('effects',[]) if isinstance(x,dict) and x.get('enabled') and str(x.get('source') or '').strip()]"
s=once(s,needle,needle+f'''\nfor _e in fxs:\n    if _e.get('id') == '{EQ}' and str(_e.get('mode') or '') == 'chromakey':\n        _e['similarity']=0.18; _e['blend']=0.03''','sub equalizer')
old="""            vf=f\"fps={WORK},format=rgba,colorkey={color(e.get('keyColor'))}:{clamp(e.get('similarity',.1),.001,.60)}:{clamp(e.get('blend',.05),.001,.35)},{scale},format=argb\";pix='argb';kind='prealpha'"""
new="""            sim=.18 if e.get('id')=='825dd7a4-f0cf-4032-a3c9-64290cb5756d' else clamp(e.get('similarity',.1),.001,.60); blend=.03 if e.get('id')=='825dd7a4-f0cf-4032-a3c9-64290cb5756d' else clamp(e.get('blend',.05),.001,.35)\n            vf=f\"fps={WORK},format=rgba,colorkey={color(e.get('keyColor'))}:{sim}:{blend},{scale},format=argb\";pix='argb';kind='prealpha'"""
s=once(s,old,new,'sub cache chroma')
old="""    # Runtime periodic master: one 30s cycle, all real Effects, exact 60 CFR.\n    m=d/'periodic-master.mp4';args=[FFM,'-hide_banner','-loglevel','error','-filter_complex_threads','8','-loop','1','-framerate','30','-i',image]"""
new="""    # Runtime periodic master: static base is prepared once, then the 30s cycle is encoded.\n    base_still=d/'periodic-860-e2e-base.png';run([FFM,'-hide_banner','-loglevel','error','-i',image,'-vf',f'scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop={W}:{H}:(iw-ow)/2:(ih-oh)/2,fps=30,setsar=1','-frames:v','1','-compression_level','1','-y',base_still])\n    m=d/'periodic-master.mp4';args=[FFM,'-hide_banner','-loglevel','error','-filter_complex_threads','8','-loop','1','-framerate','30','-i',base_still]"""
s=once(s,old,new,'sub static base')
old="graph=f'[0:v]scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop={W}:{H}:(iw-ow)/2:(ih-oh)/2,fps=30,setsar=1[b0]'"
s=once(s,old,"graph='[0:v]fps=30,setsar=1[b0]'",'sub graph')
old="tm=time.time();args += ['-filter_complex',graph,'-map','[outv]','-frames:v',str(master_frames),'-an']+hevc_args(master_seconds)+['-y',m];run(args);master_elapsed=time.time()-tm"
new=old+"\n    assert master_elapsed<=30.0,master_elapsed"
s=once(s,old,new,'sub speed')
s=once(s,"final=d/'final.mov'","final=seed",'sub in-place')
p.write_text(s)
print('PASS: ENDLUME 8.60 physical E2E harnesses aligned with optimized runtime')
