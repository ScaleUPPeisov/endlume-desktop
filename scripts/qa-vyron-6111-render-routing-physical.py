#!/usr/bin/env python3
import json, os, subprocess, sys, tempfile, time, uuid
from pathlib import Path

APP=Path(sys.argv[1]).resolve()
FFMPEG=Path(sys.argv[2]).resolve()
FFPROBE=Path(sys.argv[3]).resolve()
REPORT=Path(sys.argv[4]).resolve()
VYRON=Path(sys.argv[5]).resolve()

assert APP.is_file(), APP
assert FFMPEG.is_file() and FFPROBE.is_file(), (FFMPEG, FFPROBE)
BATCHES=(VYRON/'ProductionManager'/'Batches').resolve()
RENDER=(VYRON/'Render').resolve()
assert BATCHES.is_dir(), BATCHES
assert RENDER.is_dir(), RENDER
assert VYRON.parent.parent == Path('/Volumes'), f'VYRON_NOT_EXTERNAL={VYRON}'

preferred=['Chrome City Radio','Silent Black Room','Aegean Afterglow','Aether Riff','Afterglow Highway','Midnight Interstate']
real=[p for p in RENDER.iterdir() if p.is_dir()]
by={p.name:p for p in real}
chosen=[]
for name in preferred:
    if name in by and by[name] not in chosen: chosen.append(by[name])
for p in sorted(real,key=lambda x:x.name.lower()):
    if p not in chosen: chosen.append(p)
assert len(chosen)>=2, f'NEED_TWO_REAL_RENDER_CHANNELS={[(p.name) for p in real]}'
channels=chosen[:2]

run_id=os.environ.get('GITHUB_RUN_ID') or uuid.uuid4().hex
run_root=Path(tempfile.mkdtemp(prefix='vyron6111-routing-'))
batch=BATCHES/f'VYRON_6111_ROUTING_QA_{run_id}'
batch.mkdir(parents=True, exist_ok=False)
created_outputs=[]
project_paths=[]


def run(args, *, env=None, timeout=360, check=True):
    p=subprocess.run([str(x) for x in args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f'rc={p.returncode}: {args}\nSTDOUT:\n{p.stdout[-8000:]}\nSTDERR:\n{p.stderr[-12000:]}')
    return p


def media(project, idx):
    cover=project/'cover.png'; audio=project/'track.mp3'
    run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i',f'color=c=0x{182033+idx*222222:06x}:s=1920x1080','-frames:v','1','-y',cover])
    run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i',f'sine=frequency={440+idx*60}:sample_rate=48000:duration=8','-c:a','libmp3lame','-b:a','320k','-ar','48000','-ac','2','-y',audio])
    return cover,audio

jobs=[]
manifest_rows=[]
for idx,dest in enumerate(channels,1):
    channel=dest.name
    project=batch/f'channel-{idx}'/f'project-{idx:03}'
    project.mkdir(parents=True)
    project_paths.append(project.resolve())
    cover,audio=media(project,idx)
    status=project.parent/'status.json'; manifest=project.parent/'batch.json'
    pid=f'vyron-6111-routing-{run_id}-{idx}'
    status.write_text(json.dumps({'status':'Передано ENDLUME','projects':[{'projectId':pid,'renderStatus':'Waiting','outputFile':None}]},ensure_ascii=False,indent=2),encoding='utf-8')
    payload={
      'source':'VYRON Production Manager 6.1.11 physical QA',
      'batchId':f'{run_id}-{idx}','channelId':f'qa-{idx}','channelName':channel,
      'projectCount':1,'rootPath':str(project.parent.resolve()),'outputDir':str(dest.resolve()),
      'statusPath':str(status.resolve()),
      'projects':[{'projectId':pid,'folderPath':str(project.resolve()),'tracks':[{'path':str(audio.resolve())}]}]
    }
    manifest.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest_rows.append({'channel':channel,'manifestPath':str(manifest.resolve()),'outputDir':str(dest.resolve())})
    jobs.append({
      'project':{'id':pid,'name':f'VYRON 6.1.11 Routing QA {run_id} C{idx}','path':str(project.resolve()),'media':[str(cover.resolve())],'audio':[str(audio.resolve())],'valid':True,'error':None,'anchors':None,'selectedEffectId':'__none__','selectedEffectIds':['__none__'],'outputDir':str(dest.resolve()),'outputSource':'vyron','vyronManifestPath':str(manifest.resolve()),'vyronChannelName':channel},
      # Poison the shared setting with the forbidden project/Batches location.
      # ENDLUME must override it from persisted VYRON routing metadata before rendering.
      'settings':{'width':1920,'height':1080,'fps':60,'codec':'h265','bitrateMbps':12.0,'durationHours':8/3600,'durationMode':'whole-track','loopMode':'image','crossfadeSec':0.0,'normalizeLufs':False,'outputDir':str(project.resolve()),'preset':'fast','encoderPreference':'auto'},
      'effects':[],'subscribes':[],'ambient':None,
      'ambientSettings':{'volumePct':18.0,'bassDb':0.0,'midDb':0.0,'trebleDb':0.0}
    })

fixture=run_root/'jobs.json'; result=run_root/'result.json'
fixture.write_text(json.dumps({'jobs':jobs},ensure_ascii=False,indent=2),encoding='utf-8')
env=os.environ.copy(); env.update({'ENDLUME_E2E_RENDER_JOB':str(fixture),'ENDLUME_E2E_RESULT':str(result),'RUST_BACKTRACE':'1'})
started=time.perf_counter(); proc=run([APP],env=env,timeout=360,check=False); wall=time.perf_counter()-started
(run_root/'stdout.log').write_text(proc.stdout or '',encoding='utf-8')
(run_root/'stderr.log').write_text(proc.stderr or '',encoding='utf-8')
assert proc.returncode==0,(proc.returncode,proc.stderr[-12000:])
data=json.loads(result.read_text(encoding='utf-8')); assert data.get('status')=='passed',data
rows={r['id']:r for r in data['results']}
evidence=[]
for idx,job in enumerate(jobs,1):
    pid=job['project']['id']; expected=channels[idx-1].resolve(); project=Path(job['project']['path']).resolve()
    output=Path(rows[pid]['outputPath']).resolve()
    assert project.is_relative_to(BATCHES),(project,BATCHES)
    assert output.is_file() and output.stat().st_size>1024,output
    assert output.parent==expected,(output,expected)
    assert not output.is_relative_to(BATCHES),(output,BATCHES)
    meta=json.loads(run([FFPROBE,'-v','error','-show_entries','stream=codec_type,codec_name,width,height,avg_frame_rate:format=duration,size','-of','json',output]).stdout)
    v=next(x for x in meta['streams'] if x.get('codec_type')=='video')
    a=next(x for x in meta['streams'] if x.get('codec_type')=='audio')
    assert (v.get('width'),v.get('height'),v.get('avg_frame_rate'))==(1920,1080,'60/1'),v
    created_outputs.append(output)
    evidence.append({'channel':expected.name,'projectPath':str(project),'finalMp4Path':str(output),'bytes':output.stat().st_size,'videoCodec':v.get('codec_name'),'audioCodec':a.get('codec_name'),'duration':float(meta['format']['duration'])})

batch_media=[str(p.resolve()) for p in batch.rglob('*') if p.is_file() and p.suffix.lower() in ('.mp4','.mov','.m4v','.mkv')]
assert batch_media==[],batch_media
assert evidence[0]['finalMp4Path'] != evidence[1]['finalMp4Path']
assert Path(evidence[0]['finalMp4Path']).parent != Path(evidence[1]['finalMp4Path']).parent
stderr=proc.stderr or ''
for token in ('VYRON ROOT=','CHANNEL=','PROJECT DIRECTORY=','BATCH DIRECTORY=','FINAL RENDER DIRECTORY=','FINAL OUTPUT FILE='):
    assert token in stderr,(token,stderr[-12000:])

report={
 'status':'PASS','vyronRoot':str(VYRON),'batchesRoot':str(BATCHES),'renderRoot':str(RENDER),
 'batchPath':str(batch.resolve()),'channels':evidence,'manifestRows':manifest_rows,
 'batchesFinalMp4Count':0,'crossChannelRouting':False,'manualFolderSelection':False,
 'postRenderMove':False,'endlumeWallSeconds':wall,
 'cleanup':{'batchPath':str(batch.resolve()),'outputFiles':[str(p) for p in created_outputs]}
}
REPORT.parent.mkdir(parents=True,exist_ok=True); REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('PHYSICAL_RENDER_ROUTING=PASS')
for row in evidence:
    print('CHANNEL='+row['channel'])
    print('PROJECT_PATH='+row['projectPath'])
    print('FINAL_MP4_PATH='+row['finalMp4Path'])
print('BATCHES_FINAL_MP4_COUNT=0')
print('MANUAL_FOLDER_SELECTION=NO')
print('POST_RENDER_MOVE=NO')
