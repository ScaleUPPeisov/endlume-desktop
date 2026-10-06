#!/usr/bin/env python3
import argparse, json, os, pathlib, shutil, subprocess, time
import psutil


def run(cmd, **kwargs):
    print('+', ' '.join(map(str, cmd)), flush=True)
    return subprocess.run(cmd, check=True, **kwargs)


def ffprobe_json(ffprobe, path):
    p = subprocess.run([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], check=True, capture_output=True, text=True)
    return json.loads(p.stdout)


def media_duration(ffprobe, path):
    return float(ffprobe_json(ffprobe, path)['format']['duration'])


def make_image(ffmpeg, path):
    run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=c=0x162238:s=320x180:r=1', '-frames:v', '1', '-y', str(path)])


def make_wav(ffmpeg, path, seconds, i, variant='s16_48_stereo'):
    freq = 220 + i * 17
    base = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', f'sine=frequency={freq}:sample_rate=48000', '-t', str(seconds)]
    variants = {
        's16_48_stereo': ['-ar','48000','-ac','2','-c:a','pcm_s16le'],
        's16_44_stereo': ['-ar','44100','-ac','2','-c:a','pcm_s16le'],
        's24_48_stereo': ['-ar','48000','-ac','2','-c:a','pcm_s24le'],
        's32_48_stereo': ['-ar','48000','-ac','2','-c:a','pcm_s32le'],
        'float_48_stereo': ['-ar','48000','-ac','2','-c:a','pcm_f32le'],
        'mono': ['-ar','48000','-ac','1','-c:a','pcm_s16le'],
    }
    run(base + variants[variant] + ['-y', str(path)])


def make_mp3(ffmpeg, path, seconds, i):
    run([ffmpeg,'-hide_banner','-loglevel','error','-f','lavfi','-i',f'sine=frequency={260+i*13}:sample_rate=48000','-t',str(seconds),'-ar','48000','-ac','2','-c:a','libmp3lame','-b:a','320k','-y',str(path)])


def dir_size(path):
    total = 0
    if not path.exists(): return 0
    for p in path.rglob('*'):
        try:
            if p.is_file(): total += p.stat().st_size
        except OSError: pass
    return total


def make_job(case_id, image, audio, outdir, cf, lufs, ambient=None):
    return {
        'project': {'id':case_id,'name':case_id,'path':str(image.parent),'media':[str(image)],'audio':[str(x) for x in audio],'valid':True,'error':None},
        'settings': {'width':320,'height':180,'fps':1,'codec':'h265','bitrateMbps':0.35,'durationHours':1.0,'durationMode':'whole-track','loopMode':'none','crossfadeSec':float(cf),'normalizeLufs':bool(lufs),'outputDir':str(outdir),'preset':'fast','encoderPreference':'auto'},
        'effects': [], 'subscribes': [], 'ambient': str(ambient) if ambient else None,
    }


def smart_whole_track_duration(target, durations, crossfade):
    if not durations:
        return float(target)
    t = 0.0
    i = 0
    while t < float(target):
        add = max(0.1, float(durations[i % len(durations)]) - (float(crossfade) if t > 0.0 else 0.0))
        t += add
        i += 1
    return t


def parse_tool_commands(stderr_text):
    commands=[]
    for line in stderr_text.splitlines():
        if 'ENDLUME_1013_TOOL_CMD ' not in line: continue
        try: commands.append(json.loads(line.split('ENDLUME_1013_TOOL_CMD ',1)[1].strip()))
        except Exception: pass
    return commands


def monitor_run(app, job_path, result_path, log_prefix, cache_root):
    env=os.environ.copy(); env['ENDLUME_E2E_RENDER_JOB']=str(job_path); env['ENDLUME_E2E_RESULT']=str(result_path)
    stdout_path=pathlib.Path(str(log_prefix)+'.stdout.log'); stderr_path=pathlib.Path(str(log_prefix)+'.stderr.log')
    start_temp=dir_size(cache_root); peak_app=peak_ffmpeg=peak_temp=0; started=time.time()
    with stdout_path.open('w',encoding='utf-8') as out, stderr_path.open('w',encoding='utf-8') as err:
        p=subprocess.Popen([str(app)],env=env,stdout=out,stderr=err); proc=psutil.Process(p.pid)
        while p.poll() is None:
            try: peak_app=max(peak_app,proc.memory_info().rss); children=proc.children(recursive=True)
            except (psutil.NoSuchProcess,psutil.AccessDenied): children=[]
            for child in children:
                try:
                    if 'ffmpeg' in child.name().lower(): peak_ffmpeg=max(peak_ffmpeg,child.memory_info().rss)
                except (psutil.NoSuchProcess,psutil.AccessDenied): pass
            peak_temp=max(peak_temp,max(0,dir_size(cache_root)-start_temp)); time.sleep(0.1)
        code=p.wait()
    if code!=0: raise RuntimeError(f'ENDLUME E2E exit={code}; stderr={stderr_path.read_text(encoding="utf-8",errors="replace")[-12000:]}')
    if not result_path.exists(): raise RuntimeError('ENDLUME_E2E_RESULT missing')
    return {'wallSecondsObserved':time.time()-started,'peakEndlumeRamBytes':peak_app,'peakFfmpegRamBytes':peak_ffmpeg,'peakTempBytesObserved':peak_temp,'toolCommands':parse_tool_commands(stderr_path.read_text(encoding='utf-8',errors='replace'))}


def transition_count_for_tracks(count,width=4):
    transitions=0
    while count>1:
        nxt=0; start=0
        while start<count:
            group=min(width,count-start); transitions+=max(0,group-1); nxt+=1; start+=group
        count=nxt
    return transitions


def verify_result(ffprobe,result_path,expected_id):
    payload=json.loads(result_path.read_text(encoding='utf-8-sig'))
    if payload.get('status')!='passed': raise RuntimeError(json.dumps(payload,ensure_ascii=False,indent=2))
    results=payload.get('results',[])
    if len(results)!=1 or results[0].get('id')!=expected_id or results[0].get('status')!='passed': raise RuntimeError('Unexpected E2E result')
    r=results[0]; output=pathlib.Path(r['outputPath'])
    if not output.is_file() or output.stat().st_size<=0: raise RuntimeError(f'Missing output {output}')
    probe=ffprobe_json(ffprobe,output); aud=[x for x in probe.get('streams',[]) if x.get('codec_type')=='audio']; vid=[x for x in probe.get('streams',[]) if x.get('codec_type')=='video']
    if not aud or not vid: raise RuntimeError('Output must contain audio and video')
    a=aud[0]
    if int(a.get('sample_rate',0))!=48000 or int(a.get('channels',0))!=2: raise RuntimeError(f'Audio mismatch {a}')
    duration=float(probe['format']['duration'])
    if duration<=0: raise RuntimeError('duration <= 0')
    return {'outputPath':str(output),'outputBytes':output.stat().st_size,'durationSeconds':duration,'videoCodec':vid[0].get('codec_name'),'audioCodec':a.get('codec_name'),'sampleRate':48000,'channels':2,'productResult':r}


def analyze_bounded_commands(commands,source_tracks,cf,expect_bounded):
    ff=[x for x in commands if x.get('name')=='ffmpeg']; stages=[str(x.get('stage','')) for x in ff]
    pre=[x for x in ff if str(x.get('stage','')).startswith('normalize WAV') or str(x.get('stage','')).startswith('bounded crossfade round') or str(x.get('stage',''))=='bounded final HQ MP3']
    max_inputs=max([sum(1 for a in x.get('args',[]) if a=='-i') for x in pre] or [0]); normalizations=sum(1 for s in stages if s.startswith('normalize WAV')); final_hq=sum(1 for s in stages if s=='bounded final HQ MP3')
    cross=concat=0
    import re
    for x in pre:
        args=x.get('args',[])
        for i,arg in enumerate(args):
            if arg=='-filter_complex' and i+1<len(args):
                graph=args[i+1]; cross+=graph.count('acrossfade=')
                for n in re.findall(r'concat=n=(\d+)',graph): concat+=max(0,int(n)-1)
    expected=transition_count_for_tracks(source_tracks,4)
    if expect_bounded:
        if normalizations!=source_tracks: raise RuntimeError(f'Expected {source_tracks} normalization commands, observed {normalizations}')
        if final_hq!=1 or max_inputs>4: raise RuntimeError(f'bounded command gate final={final_hq} maxInputs={max_inputs}')
        actual=cross if cf>0.01 else concat
        if actual!=expected: raise RuntimeError(f'Transition mismatch expected={expected} actual={actual}')
        return {'audioBounded1013':True,'sourceTracks':source_tracks,'maxSimultaneousInputs':max_inputs,'transitionCount':actual,'expectedTransitions':expected,'normalizationCommands':normalizations,'boundedFinalCommands':final_hq}
    if pre: raise RuntimeError(f'MP3 regression unexpectedly entered bounded path: {stages}')
    return {'audioBounded1013':False,'sourceTracks':source_tracks,'maxSimultaneousInputs':0,'transitionCount':0}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('app'); ap.add_argument('ffmpeg'); ap.add_argument('ffprobe'); ap.add_argument('outdir'); ap.add_argument('--mode',choices=['fast','long'],default='fast'); ns=ap.parse_args()
    app=pathlib.Path(ns.app).resolve(); ffmpeg=str(pathlib.Path(ns.ffmpeg).resolve()); ffprobe=str(pathlib.Path(ns.ffprobe).resolve()); root=pathlib.Path(ns.outdir).resolve()
    if root.exists(): shutil.rmtree(root)
    for d in ['fixture','outputs','results']: (root/d).mkdir(parents=True)
    image=root/'fixture'/'visual.png'; make_image(ffmpeg,image); cache_root=pathlib.Path(os.environ.get('LOCALAPPDATA',root))/'studio.endlume.desktop'
    matrix={1:0,2:1,4:3,5:4,8:7,20:19,30:29}
    for tracks,expected in matrix.items():
        actual=transition_count_for_tracks(tracks,4)
        if actual!=expected: raise RuntimeError(f'transition regression tracks={tracks} expected={expected} actual={actual}')
    summary={'mode':ns.mode,'status':'RED','transitionRegression':{str(k):transition_count_for_tracks(k,4) for k in matrix},'cases':[]}
    if ns.mode=='long':
        tracks=[]
        for i in range(1,21):
            p=root/'fixture'/f'long-{i:02d}.wav'; make_wav(ffmpeg,p,120,i); tracks.append(p)
        cases=[('long-20wav-cf10-lufs',tracks,10,True,None,True)]
    else:
        wav=[]
        for i in range(1,21): p=root/'fixture'/f'wav-{i:02d}.wav'; make_wav(ffmpeg,p,30,i); wav.append(p)
        variants=['s16_48_stereo','s16_44_stereo','s24_48_stereo','s32_48_stereo','float_48_stereo','mono']; mixed=[]
        for i in range(1,21): p=root/'fixture'/f'mixed-{i:02d}.wav'; make_wav(ffmpeg,p,30,i+30,variants[(i-1)%len(variants)]); mixed.append(p)
        mp3=[]
        for i in range(1,21): p=root/'fixture'/f'mp3-{i:02d}.mp3'; make_mp3(ffmpeg,p,30,i+60); mp3.append(p)
        ambient=root/'fixture'/'ambient.mp3'; make_mp3(ffmpeg,ambient,12,99)
        cases=[('wav-cf0',wav,0,False,None,True),('wav-cf5',wav,5,False,None,True),('wav-cf10',wav,10,False,None,True),('wav-cf5-lufs',wav,5,True,None,True),('wav-cf10-lufs',wav,10,True,None,True),('mixed-wav-cf10-lufs',mixed,10,True,None,True),('wav-cf10-ambient',wav,10,False,ambient,True),('mp3-regression',mp3,0,False,None,False)]
    global_max=0
    for case_id,tracks,cf,lufs,ambient,expect_bounded in cases:
        job=make_job(case_id,image,tracks,root/'outputs',cf,lufs,ambient)
        job_path=root/'results'/f'{case_id}.job.json'; result_path=root/'results'/f'{case_id}.result.json'; job_path.write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
        resource=monitor_run(app,job_path,result_path,root/'results'/case_id,cache_root); verified=verify_result(ffprobe,result_path,case_id); bounded=analyze_bounded_commands(resource['toolCommands'],len(tracks),cf,expect_bounded)
        if expect_bounded:
            source_durations=[media_duration(ffprobe,x) for x in tracks]
            target=float(job['settings']['durationHours'])*3600.0
            expected_audio=smart_whole_track_duration(target,source_durations,float(cf))
            observed=float(verified['durationSeconds']); tol=max(expected_audio*0.003,0.75)
            if abs(observed-expected_audio)>tol: raise RuntimeError(f'{case_id}: duration expected={expected_audio:.3f} output={observed:.3f} tolerance={tol:.3f}')
            bounded['expectedAudioDuration']=expected_audio; bounded['verifiedOutputDuration']=observed
        global_max=max(global_max,bounded['maxSimultaneousInputs']); record={'id':case_id,**verified,'audio1013':bounded,**resource}; summary['cases'].append(record)
        print('CASE_GREEN',case_id,json.dumps({'wall':resource['wallSecondsObserved'],'peakEndlumeRam':resource['peakEndlumeRamBytes'],'peakFfmpegRam':resource['peakFfmpegRamBytes'],'maxInputs':bounded['maxSimultaneousInputs'],'transitionCount':bounded['transitionCount']}),flush=True)
    summary['maxSimultaneousAudioInputsObserved']=global_max; summary['status']='GREEN'; (root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8'); print('ENDLUME_1013_WINDOWS_PRODUCT_E2E_GREEN',ns.mode,'maxInputs=',global_max)


if __name__=='__main__': main()
