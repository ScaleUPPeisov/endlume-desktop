#!/usr/bin/env python3
import json,subprocess,sys,tempfile,time
from pathlib import Path
SIDE=Path(sys.argv[1]).resolve(); FFM=Path(sys.argv[2]).resolve(); FFP=Path(sys.argv[3]).resolve(); OUT=Path(sys.argv[4]).resolve()
EQ='825dd7a4-f0cf-4032-a3c9-64290cb5756d'
d=json.loads(SIDE.read_text(errors='replace'))
img=Path(d['project']['media'][0]); fx=[e for e in d.get('effects',[]) if isinstance(e,dict) and e.get('enabled') and str(e.get('source') or '').strip()]
assert img.is_file() and len(fx)>=2

def sh(a): return subprocess.check_output(list(map(str,a)),text=True).strip()
def run(a): subprocess.run(list(map(str,a)),check=True)
def even(v):
    n=max(2,int(round(v))); return n if n%2==0 else n+1
def clamp(v,a,b): return max(a,min(b,float(v)))
def col(e): return '0x'+str(e.get('keyColor') or '00ff00').lstrip('#')

variants=[
 ('baseline_rt1_prio0_t8',1,0,8),
 ('rt0_prio0_t8',0,0,8),
 ('rt0_prio0_t4',0,0,4),
 ('rt0_prio0_t2',0,0,2),
 ('rt1_prio1_t8',1,1,8),
 ('rt0_prio1_t8',0,1,8),
]
with tempfile.TemporaryDirectory(prefix='e861-vt-probe-') as td:
    td=Path(td);base=td/'base.png'
    run([FFM,'-hide_banner','-loglevel','error','-i',img,'-vf','scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop=1920:1080:(iw-ow)/2:(ih-oh)/2,fps=30,setsar=1','-frames:v','1','-compression_level','1','-y',base])
    cached=[];dur=[]
    for i,e in enumerate(fx[:2],1):
        sim=.18 if e.get('id')==EQ else clamp(e.get('similarity',.1),.001,.60)
        blend=.03 if e.get('id')==EQ else clamp(e.get('blend',.05),.001,.35)
        target=even(1920*clamp(e.get('scale',1),.05,1.5))
        vf=f"fps=30,format=rgba,colorkey={col(e)}:{sim}:{blend},scale={target}:-2:flags=lanczos,format=argb"
        p=td/f'fx{i}.mov';run([FFM,'-hide_banner','-loglevel','error','-i',e['source'],'-vf',vf,'-an','-c:v','qtrle','-pix_fmt','argb','-y',p]);cached.append((p,e))
        try: dur.append(float(sh([FFP,'-v','error','-show_entries','format=duration','-of','csv=p=0',e['source']])))
        except Exception: dur.append(12.0)
    seconds=max([12.0]+[max(2.0,min(60.0,x)) for x in dur]);frames=round(seconds*60)
    graph='[0:v]fps=30,setsar=1[b0]';last='b0'
    for i,(_,e) in enumerate(cached,1):
        x=f"max(0,min(W-w,W*{clamp(e.get('x',.5),0,1)}-w/2))";y=f"max(0,min(H-h,H*{clamp(e.get('y',.5),0,1)}-h/2))"
        graph+=f";[{i}:v]fps=30,setpts=PTS-STARTPTS,format=argb[fx{i}];[{last}][fx{i}]overlay=x='{x}':y='{y}':shortest=0:repeatlast=1:eof_action=repeat:format=auto:eval=init[b{i}]";last=f'b{i}'
    graph+=f';[{last}]fps=60,format=yuv420p[outv]'
    records=[]
    for name,rt,prio,threads in variants:
        p=td/f'{name}.mp4';args=[FFM,'-hide_banner','-loglevel','error','-filter_complex_threads',str(threads),'-loop','1','-framerate','30','-i',base]
        for cp,_ in cached: args += ['-stream_loop','-1','-i',cp]
        args += ['-filter_complex',graph,'-map','[outv]','-frames:v',str(frames),'-an','-c:v','hevc_videotoolbox','-realtime',str(rt),'-prio_speed',str(prio),'-power_efficient','0','-q:v','100','-b:v','500k','-maxrate','12M','-bufsize','64M','-g','1800','-tag:v','hvc1','-pix_fmt','yuv420p','-fps_mode','cfr','-r','60','-video_track_timescale','60000','-y',p]
        t=time.monotonic();run(args);dt=time.monotonic()-t
        fr=int(sh([FFP,'-v','error','-select_streams','v:0','-count_frames','-show_entries','stream=nb_read_frames','-of','csv=p=0',p]));pk=int(sh([FFP,'-v','error','-select_streams','v:0','-count_packets','-show_entries','stream=nb_read_packets','-of','csv=p=0',p]))
        st=json.loads(sh([FFP,'-v','error','-select_streams','v:0','-show_entries','stream=codec_name,pix_fmt,width,height,avg_frame_rate','-of','json',p]))['streams'][0]
        rec={'name':name,'seconds':round(dt,3),'frames':fr,'packets':pk,'stream':st};print('PROBE',json.dumps(rec,ensure_ascii=False),flush=True)
        assert fr==frames and pk==frames,rec
        assert st.get('codec_name')=='hevc' and st.get('pix_fmt')=='yuv420p' and st.get('width')==1920 and st.get('height')==1080 and st.get('avg_frame_rate')=='60/1',rec
        records.append(rec);p.unlink(missing_ok=True);time.sleep(2)
    fastest=min(records,key=lambda x:x['seconds'])
    safe=min([x for x in records if 'prio0' in x['name']],key=lambda x:x['seconds'])
    doc={'status':'passed','frames':frames,'master_duration':seconds,'records':records,'fastest':fastest,'fastest_no_quality_tradeoff':safe}
    OUT.write_text(json.dumps(doc,ensure_ascii=False,indent=2));print('FASTEST_SAFE',json.dumps(safe,ensure_ascii=False),flush=True)
