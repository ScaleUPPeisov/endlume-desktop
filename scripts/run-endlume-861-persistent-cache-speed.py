#!/usr/bin/env python3
import hashlib,json,os,subprocess,sys,tempfile,time
from pathlib import Path
SIDE=Path(sys.argv[1]).resolve(); FFM=Path(sys.argv[2]).resolve(); FFP=Path(sys.argv[3]).resolve(); OUT=Path(sys.argv[4]).resolve()
EQ='825dd7a4-f0cf-4032-a3c9-64290cb5756d'
d=json.loads(SIDE.read_text(errors='replace')); img=Path(d['project']['media'][0]); fx=[e for e in d.get('effects',[]) if isinstance(e,dict) and e.get('enabled') and str(e.get('source') or '').strip()]
assert img.is_file() and len(fx)>=2

def sh(a): return subprocess.check_output(list(map(str,a)),text=True,stderr=subprocess.STDOUT).strip()
def run(a): subprocess.run(list(map(str,a)),check=True)
def clamp(v,a,b): return max(a,min(b,float(v)))
def rnum(v):
    v=float(v)
    if v.is_integer(): return str(int(v))
    return format(v,'.15g')
def rbool(v): return 'true' if bool(v) else 'false'
def cache_key(e):
    p=Path(e['source']); st=p.stat(); sim=.18 if e.get('id')==EQ else clamp(e.get('similarity',.1),.001,.60); blend=.03 if e.get('id')==EQ else clamp(e.get('blend',.05),.001,.35)
    vals=['strict-860',str(p),str(st.st_size),str(int(st.st_mtime)), '30','1920','1080',str(e.get('mode') or 'chromakey'),str(e.get('keyColor') or '#00ff00'),rnum(sim),rnum(blend),rnum(e.get('lumaThreshold',.03)),rnum(e.get('lumaTolerance',.08)),rnum(e.get('scale',1)),rbool(e.get('fullscreen',False)),rnum(e.get('saturation',1))]
    return hashlib.sha256('|'.join(vals).encode()).hexdigest()[:24]
cache_root=Path.home()/'Library'/'Caches'/'studio.endlume.desktop'/'strict-effects-856'
with tempfile.TemporaryDirectory(prefix='e861-fast-') as td:
    td=Path(td); base=td/'base.png'
    run([FFM,'-hide_banner','-loglevel','error','-i',img,'-vf','scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop=1920:1080:(iw-ow)/2:(ih-oh)/2,setsar=1','-frames:v','1','-compression_level','1','-y',base])
    cached=[]; durations=[]
    for e in fx[:2]:
        key=cache_key(e); p=cache_root/f'{key}.mov'
        if not p.is_file():
            candidates=sorted(cache_root.glob('*.mov'),key=lambda x:x.stat().st_mtime,reverse=True) if cache_root.is_dir() else []
            raise SystemExit(f'MISSING_STRICT_CACHE key={key} path={p} candidates={len(candidates)}')
        cached.append((p,e))
        try: durations.append(float(sh([FFP,'-v','error','-show_entries','format=duration','-of','csv=p=0',p])))
        except Exception: durations.append(12.0)
    seconds=max([12.0]+[max(2.0,min(60.0,x)) for x in durations]); frames=round(seconds*60)
    variants=[('production',False),('single_decode_lean',True),('single_decode_lean_repeat',True)]
    recs=[]; keep={}
    for name,opt in variants:
        graph='[0:v]fps=30,setsar=1[b0]' if not opt else '[0:v]loop=loop=-1:size=1:start=0,setpts=N/(30*TB),setsar=1[b0]'; last='b0'
        for i,(_,e) in enumerate(cached,1):
            x=f"max(0,min(W-w,W*{clamp(e.get('x',.5),0,1)}-w/2))"; y=f"max(0,min(H-h,H*{clamp(e.get('y',.5),0,1)}-h/2))"
            prep=f'[{i}:v]fps=30,setpts=PTS-STARTPTS,format=argb[fx{i}]' if not opt else f'[{i}:v]setpts=PTS-STARTPTS[fx{i}]'
            graph+=f";{prep};[{last}][fx{i}]overlay=x='{x}':y='{y}':shortest=0:repeatlast=1:eof_action=repeat:format=auto:eval=init[b{i}]"; last=f'b{i}'
        graph+=f';[{last}]fps=60,format=yuv420p[outv]'
        p=td/f'{name}.mp4'; args=[FFM,'-hide_banner','-loglevel','error','-filter_complex_threads','8']
        args += (['-loop','1','-framerate','30','-i',base] if not opt else ['-i',base])
        for cp,_ in cached: args += ['-stream_loop','-1','-i',cp]
        args += ['-filter_complex',graph,'-map','[outv]','-frames:v',str(frames),'-an','-c:v','hevc_videotoolbox','-realtime','1','-prio_speed','0','-power_efficient','0','-q:v','100','-b:v','500k','-maxrate','12M','-bufsize','64M','-g','1800','-tag:v','hvc1','-pix_fmt','yuv420p','-fps_mode','cfr','-r','60','-video_track_timescale','60000','-y',p]
        t=time.monotonic(); run(args); dt=time.monotonic()-t
        fr=int(sh([FFP,'-v','error','-select_streams','v:0','-count_frames','-show_entries','stream=nb_read_frames','-of','csv=p=0',p])); pk=int(sh([FFP,'-v','error','-select_streams','v:0','-count_packets','-show_entries','stream=nb_read_packets','-of','csv=p=0',p])); st=json.loads(sh([FFP,'-v','error','-select_streams','v:0','-show_entries','stream=codec_name,pix_fmt,width,height,avg_frame_rate','-of','json',p]))['streams'][0]
        rec={'name':name,'seconds':round(dt,3),'frames':fr,'packets':pk,'stream':st}; print('PROBE',json.dumps(rec,ensure_ascii=False),flush=True)
        assert fr==frames and pk==frames; assert st.get('codec_name')=='hevc' and st.get('pix_fmt')=='yuv420p' and st.get('width')==1920 and st.get('height')==1080 and st.get('avg_frame_rate')=='60/1'
        recs.append(rec); keep[name]=p
        time.sleep(2)
    base_t=recs[0]['seconds']; opt_times=[x['seconds'] for x in recs[1:]]; best=min(opt_times)
    assert best<=30.0, recs
    # Decode equivalence spot-check: same composition, same dimensions/fps; compare first 5s with SSIM.
    cmp=sh([FFM,'-hide_banner','-i',keep['production'],'-i',keep['single_decode_lean'],'-lavfi','[0:v][1:v]ssim','-t','5','-f','null','-'])
    import re
    m=re.findall(r'All:([0-9.]+)',cmp); ssim=float(m[-1]) if m else 0.0
    assert ssim>=0.995, {'ssim':ssim,'log':cmp[-2000:]}
    doc={'status':'passed','master_duration':seconds,'frames':frames,'records':recs,'best_seconds':best,'baseline_seconds':base_t,'ssim_5s':ssim,'cache_root':str(cache_root)}
    OUT.write_text(json.dumps(doc,ensure_ascii=False,indent=2)); print(json.dumps(doc,ensure_ascii=False,indent=2))
