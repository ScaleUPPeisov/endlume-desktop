#!/usr/bin/env python3
import json,math,os,subprocess,sys,tempfile,time
from pathlib import Path

SIDE=Path(sys.argv[1]).resolve();SUBJSON=Path(sys.argv[2]).resolve();FFM=Path(sys.argv[3]).resolve();FFP=Path(sys.argv[4]).resolve();METRICS=Path(sys.argv[5]).resolve()
ROOT=Path(__file__).resolve().parents[1]
W,H,FPS,WORK=1920,1080,60,30
EQ='825dd7a4-f0cf-4032-a3c9-64290cb5756d'

def log(*a): print('[e860-sub]',*a,flush=True)
def run(a,*,capture=False,env=None,cwd=None):
    a=[str(x) for x in a];log('RUN',' '.join(a[:10])+(' ...' if len(a)>10 else ''))
    return subprocess.run(a,check=True,stdout=subprocess.PIPE if capture else None,stderr=subprocess.PIPE if capture else None,env=env,cwd=cwd)
def out(a): return run(a,capture=True).stdout.decode(errors='replace').strip()
def dur(p): return float(out([FFP,'-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',p]))
def frames(p): return int(out([FFP,'-v','error','-select_streams','v:0','-count_frames','-show_entries','stream=nb_read_frames','-of','default=nw=1:nk=1',p]))
def packets(p): return int(out([FFP,'-v','error','-select_streams','v:0','-count_packets','-show_entries','stream=nb_read_packets','-of','default=nw=1:nk=1',p]))
def probe(p): return json.loads(out([FFP,'-v','error','-show_entries','stream=codec_type,codec_name,pix_fmt,width,height,avg_frame_rate,nb_frames,sample_rate,channels','-of','json',p]))['streams']
def clamp(v,a,b): return max(a,min(b,float(v)))
def even(v):
    n=max(2,int(round(v)));return n if n%2==0 else n+1
def color(v): return '0x'+str(v or '00ff00').strip().lstrip('#').removeprefix('0x')
def esc(p): return str(p).replace("'","'\\''")
def hevc_args(seconds):
    g=min(max(1,int(round(seconds*FPS))),1800)
    return ['-c:v','hevc_videotoolbox','-realtime','1','-prio_speed','0','-power_efficient','0','-q:v','100','-b:v','500k','-maxrate','12M','-bufsize','64M','-g',str(g),'-tag:v','hvc1','-pix_fmt','yuv420p','-fps_mode','cfr','-r','60','-video_track_timescale','60000']
def copy_slice(src,start_frame,n,outp):
    if n<=0:return
    run([FFM,'-hide_banner','-loglevel','error','-stream_loop','-1','-ss',f'{start_frame/FPS:.9f}','-i',src,'-frames:v',str(n),'-an','-c:v','copy','-avoid_negative_ts','make_zero','-y',outp])
    assert frames(outp)==n,(outp,frames(outp),n)
def pad(p):
    n=p.stat().st_size
    if n>700_000_000: raise RuntimeError(f'final >700MB: {n}')
    if n<500_000_000:
        add=500_000_000-n
        if add<8 or add>0xffffffff: raise RuntimeError(f'bad free atom {add}')
        with p.open('ab') as f:
            f.write(add.to_bytes(4,'big'));f.write(b'free');f.truncate(500_000_000);f.flush();os.fsync(f.fileno())
    return p.stat().st_size

data=json.loads(SIDE.read_text(errors='replace'));sub=json.loads(SUBJSON.read_text(errors='replace'))
image=Path(data['project']['media'][0]);audios=[Path(x) for x in data['project']['audio']]
fxs=[x for x in data.get('effects',[]) if isinstance(x,dict) and x.get('enabled') and str(x.get('source') or '').strip()]
assert image.is_file() and len(audios)==15 and all(x.is_file() for x in audios) and len(fxs)>=2
srcsub=Path(sub['source']);assert srcsub.is_file(),srcsub
first=float(sub['firstAtSec']);second=float(sub['secondAtSec']);repeat=float(sub['repeatEverySec'])
assert repeat>=60,(first,second,repeat)
first0=min(first,second);anchor=max(first,second);repeat_frames=int(round(repeat*FPS));first_frames=int(round(first0*FPS));anchor_frames=int(round(anchor*FPS))
# Pick a repeat divisor closest to 30 s, exactly as runtime periodic planner.
best=None
for n in range(20*FPS,40*FPS+1):
    if repeat_frames%n==0:
        d=abs(n-30*FPS)
        if best is None or d<best[0]:best=(d,n)
assert best is not None,(repeat,repeat_frames)
master_frames=best[1];master_seconds=master_frames/FPS
assert anchor_frames<master_frames and first_frames<=anchor_frames
metrics={'status':'started','release_gate':False,'subscribe_on_gate':False,'preset':sub,'master_seconds_planned':master_seconds}
METRICS.write_text(json.dumps(metrics,ensure_ascii=False,indent=2))

with tempfile.TemporaryDirectory(prefix='e860-sub-') as td:
    d=Path(td);cached=[]
    # Strict Effects cache with 8.59/8.60 protected equalizer values.
    for i,e in enumerate(fxs[:2],1):
        src=Path(e['source']);target=even(W*clamp(e.get('scale',1),.05,1.5));mode=str(e.get('mode') or 'chromakey')
        scale=(f'scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black@0' if e.get('fullscreen') else f'scale={target}:-2:flags=lanczos')
        if mode in ('screen','screen-cache','strict-screen-cache'):
            vf=f'fps={WORK},format=rgb24,{scale}';pix='rgb24';kind='screen'
        elif mode=='luma':
            vf=f"fps={WORK},format=rgba,lumakey=threshold={e.get('lumaThreshold',.1)}:tolerance={e.get('lumaTolerance',.1)}:softness=.08,{scale},format=argb";pix='argb';kind='prealpha'
        else:
            sim=.18 if e.get('id')==EQ else clamp(e.get('similarity',.1),.001,.60);blend=.03 if e.get('id')==EQ else clamp(e.get('blend',.05),.001,.35)
            vf=f"fps={WORK},format=rgba,colorkey={color(e.get('keyColor'))}:{sim}:{blend},{scale},format=argb";pix='argb';kind='prealpha'
        dst=d/f'fx{i}.mov';run([FFM,'-hide_banner','-loglevel','error','-i',src,'-vf',vf,'-an','-c:v','qtrle','-pix_fmt',pix,'-y',dst]);cached.append((dst,e,kind))

    base=d/'periodic-860-base.png';run([FFM,'-hide_banner','-loglevel','error','-i',image,'-vf',f'scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop={W}:{H}:(iw-ow)/2:(ih-oh)/2,fps=30,setsar=1','-frames:v','1','-compression_level','1','-y',base])
    master=d/'periodic-master.mp4';args=[FFM,'-hide_banner','-loglevel','error','-filter_complex_threads','8','-loop','1','-framerate','30','-i',base]
    for p,_,_ in cached:args+=['-stream_loop','-1','-i',p]
    graph='[0:v]fps=30,setsar=1[b0]';last='b0'
    for i,(_,e,kind) in enumerate(cached,1):
        fx=f'fx{i}';nxt=f'b{i}';x=f"max(0,min(W-w,W*{clamp(e.get('x',.5),0,1)}-w/2))";y=f"max(0,min(H-h,H*{clamp(e.get('y',.5),0,1)}-h/2))"
        if kind=='screen':
            px='0' if e.get('fullscreen') else f"max(0,min(ow-iw,ow*{clamp(e.get('x',.5),0,1)}-iw/2))";py='0' if e.get('fullscreen') else f"max(0,min(oh-ih,oh*{clamp(e.get('y',.5),0,1)}-ih/2))"
            graph+=f";[{i}:v]fps=30,format=rgb24,pad={W}:{H}:'{px}':'{py}':color=black[{fx}];[{last}][{fx}]blend=all_mode=screen:all_opacity=1[{nxt}]"
        else:
            graph+=f";[{i}:v]fps=30,setpts=PTS-STARTPTS,format=argb[{fx}];[{last}][{fx}]overlay=x='{x}':y='{y}':shortest=0:repeatlast=1:eof_action=repeat:format=auto[{nxt}]"
        last=nxt
    graph+=f';[{last}]fps=60,format=yuv420p[outv]'
    t=time.time();args+=['-filter_complex',graph,'-map','[outv]','-frames:v',str(master_frames),'-an']+hevc_args(master_seconds)+['-y',master];run(args);master_elapsed=time.time()-t
    assert master_elapsed<=30.0,master_elapsed
    assert frames(master)==master_frames and packets(master)==master_frames,(frames(master),packets(master),master_frames)

    # Render a real Subscribe segment over the master; after EOF the base passes through.
    sd=dur(srcsub);sub_frames=max(1,int(math.ceil(sd*FPS)))
    def render_sub(start_frame,n,label):
        phase=start_frame/FPS;o=d/f'sub-{label}.mp4';target=even(W*clamp(sub.get('scale',1),.05,1.5));x=f"max(0,min(W-w,W*{clamp(sub.get('x',.5),0,1)}-w/2))";y=f"max(0,min(H-h,H*{clamp(sub.get('y',.5),0,1)}-h/2))"
        mode=str(sub.get('mode') or 'chromakey')
        if mode in ('screen','screen-cache','strict-screen-cache'):
            prep=f'[1:v]fps=30,format=rgb24,scale={target}:-2:flags=lanczos[s]';mix=f"[b][s]blend=all_mode=screen:all_opacity=1[o]"
        else:
            prep=f"[1:v]fps=30,format=rgba,colorkey={color(sub.get('keyColor'))}:{clamp(sub.get('similarity',.1),.001,.60)}:{clamp(sub.get('blend',.05),.001,.35)},scale={target}:-2:flags=lanczos[s]";mix=f"[b][s]overlay=x='{x}':y='{y}':shortest=0:repeatlast=0:eof_action=pass:format=auto[o]"
        g=f'[0:v]fps=30,setpts=PTS-STARTPTS[b];{prep};{mix};[o]fps=60,format=yuv420p[v]';sec=n/FPS
        run([FFM,'-hide_banner','-loglevel','error','-stream_loop','-1','-ss',f'{phase:.9f}','-i',master,'-i',srcsub,'-filter_complex',g,'-map','[v]','-frames:v',str(n),'-an']+hevc_args(sec)+['-y',o])
        assert frames(o)==n and packets(o)==n,(label,frames(o),packets(o),n);return o

    parts=[]
    if first_frames<anchor_frames:
        if first_frames:
            p=d/'prefix-head.mp4';copy_slice(master,0,first_frames,p);parts.append(p)
        parts.append(render_sub(first_frames,anchor_frames-first_frames,'first'))
    elif anchor_frames:
        p=d/'prefix-head.mp4';copy_slice(master,0,anchor_frames,p);parts.append(p)
    phase=anchor_frames%master_frames;cycle_sub=(master_frames-phase)%master_frames or master_frames
    while cycle_sub<sub_frames:cycle_sub+=master_frames
    assert cycle_sub<repeat_frames,(cycle_sub,repeat_frames)
    parts.append(render_sub(phase,cycle_sub,'cycle'))
    remain=repeat_frames-cycle_sub;full=remain//master_frames;tail=remain%master_frames
    parts += [master]*full
    if tail:
        p=d/'cycle-tail.mp4';copy_slice(master,0,tail,p);parts.append(p)
    lst=d/'parts.txt';lst.write_text(''.join(f"file '{esc(p)}'\n" for p in parts));seed_video=d/'seed-video.mp4'
    run([FFM,'-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',lst,'-an','-c:v','copy','-avoid_negative_ts','make_zero','-y',seed_video])
    expected=anchor_frames+repeat_frames;assert frames(seed_video)==expected and packets(seed_video)==expected,(frames(seed_video),packets(seed_video),expected)

    # Untouched MP3 packet-copy cycle and whole-song duration.
    sigs=[];tds=[];clean=[]
    for i,a in enumerate(audios,1):
        sig=out([FFP,'-v','error','-select_streams','a:0','-show_entries','stream=codec_name,sample_rate,channels','-of','csv=p=0:s=|',a]).split('|');sigs.append(sig);tds.append(dur(a));c=d/f'a{i:02}.mp3';run([FFM,'-hide_banner','-loglevel','error','-i',a,'-map','0:a:0','-c:a','copy','-map_metadata','-1','-write_xing','0','-id3v2_version','0','-y',c]);clean.append(c)
    assert all(x==sigs[0] and x[0]=='mp3' for x in sigs),sigs
    al=d/'audio-list.txt';al.write_text('\n'.join(str(x) for x in clean)+'\n');cycle=d/'audio.mp3';run([FFM,'-hide_banner','-loglevel','error','-fflags','+genpts','-i',f'concatf:{al}','-map','0:a:0','-c:a','copy','-map_metadata','-1','-write_xing','0','-id3v2_version','0','-y',cycle])
    target=float((data.get('settings') or {}).get('durationHours',2))*3600;t=0.0;i=0
    while t<target:t+=max(.1,tds[i%len(tds)]);i+=1
    final_duration=t;total_frames=max(expected,int(round(final_duration*FPS)))
    seed=d/'seed.mov';run([FFM,'-hide_banner','-loglevel','error','-i',seed_video,'-stream_loop','-1','-fflags','+genpts','-i',cycle,'-t',f'{final_duration:.9f}','-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','copy','-y',seed])
    env=os.environ.copy();env.update({'ENDLUME_MANIFEST_SEED':str(seed),'ENDLUME_MANIFEST_OUT':str(seed),'ENDLUME_MANIFEST_PREFIX_FRAMES':str(anchor_frames),'ENDLUME_MANIFEST_CYCLE_FRAMES':str(repeat_frames),'ENDLUME_MANIFEST_TOTAL_FRAMES':str(total_frames)})
    run(['cargo','test','--manifest-path','src-tauri/Cargo.toml','external_prefix_cycle_manifest_if_requested','--','--nocapture'],env=env,cwd=ROOT)
    size=pad(seed);ss=probe(seed);v=next(x for x in ss if x.get('codec_type')=='video');a=next(x for x in ss if x.get('codec_type')=='audio');fd=dur(seed)
    assert v.get('codec_name')=='hevc' and v.get('pix_fmt')=='yuv420p' and v.get('width')==W and v.get('height')==H and v.get('avg_frame_rate')=='60/1',v
    assert a.get('codec_name')=='mp3',a
    assert abs(fd-final_duration)<=1.0,(fd,final_duration)
    assert 500_000_000<=size<=700_000_000,size
    points=[max(0,first0-.25),first0+.25,max(0,anchor-.25),anchor+.25,anchor+repeat-.25,anchor+repeat+.25,final_duration/2,max(0,final_duration-2)]
    for pnt in points:run([FFM,'-hide_banner','-loglevel','error','-ss',f'{pnt:.3f}','-i',seed,'-map','0:v:0','-frames:v','2','-f','null','-'])
    run([FFM,'-hide_banner','-loglevel','error','-ss',f'{max(0,final_duration-2):.3f}','-i',seed,'-map','0:a:0','-t','0.25','-f','null','-'])
    metrics.update({'status':'passed','release_gate':True,'subscribe_on_gate':True,'master_seconds':round(master_elapsed,3),'master_frames':master_frames,'master_packets':master_frames,'final_duration':round(fd,6),'final_bytes':size,'audio_codec':'mp3','resolution':'1920x1080','fps':'60/1','seek_points':len(points),'whole_track':True,'in_place_manifest':True})
    METRICS.write_text(json.dumps(metrics,ensure_ascii=False,indent=2));log('PASS',json.dumps(metrics,ensure_ascii=False))
