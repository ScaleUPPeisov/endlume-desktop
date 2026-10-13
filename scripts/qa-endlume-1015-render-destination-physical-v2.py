#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

APP=Path(sys.argv[1]).resolve()
FFMPEG=Path(sys.argv[2]).resolve()
FFPROBE=Path(sys.argv[3]).resolve()
REPORT=Path(sys.argv[4]).resolve()
VYRON=Path(sys.argv[5]).resolve()

assert APP.is_file(), APP
assert FFMPEG.is_file() and FFPROBE.is_file(), (FFMPEG,FFPROBE)
assert VYRON.is_dir(), f'VYRON_ROOT_NOT_FOUND={VYRON}'
BATCHES=VYRON/'ProductionManager'/'Batches'
RENDER=VYRON/'Render'
assert BATCHES.is_dir(), f'VYRON_BATCHES_NOT_FOUND={BATCHES}'
assert RENDER.is_dir(), f'VYRON_RENDER_NOT_FOUND={RENDER}'
assert VYRON.parent.name and VYRON.parent.parent==Path('/Volumes'), f'VYRON_ROOT_NOT_ON_EXTERNAL_VOLUME={VYRON}'
EXTERNAL_VOLUME=VYRON.parent

CHANNELS=['Aegean Afterglow','Aether Riff','Afterglow Highway']
for channel in CHANNELS:
    assert (RENDER/channel).is_dir(), f'EXISTING_CHANNEL_RENDER_FOLDER_NOT_FOUND={RENDER/channel}'

run_root=Path(tempfile.mkdtemp(prefix='endlume1015-routing-'))
created_batches=[]
created_outputs=[]


def run(args, *, env=None, timeout=300, check=True):
    p=subprocess.run([str(x) for x in args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,timeout=timeout)
    if check and p.returncode!=0:
        raise RuntimeError(f'rc={p.returncode}: {args}\nSTDOUT:\n{p.stdout[-8000:]}\nSTDERR:\n{p.stderr[-12000:]}')
    return p


def make_media(project_dir,idx):
    cover=project_dir/'cover.png'
    audio=project_dir/'track.mp3'
    run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i',f'color=c=0x{182033+idx*111111:06x}:s=1920x1080','-frames:v','1','-y',cover])
    run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i',f'sine=frequency={420+idx*40}:sample_rate=48000:duration=10','-c:a','libmp3lame','-b:a','320k','-ar','48000','-ac','2','-y',audio])
    return cover,audio


def settings(poisoned_output):
    return {'width':1920,'height':1080,'fps':60,'codec':'h265','bitrateMbps':30.0,'durationHours':10/3600,'durationMode':'whole-track','loopMode':'image','crossfadeSec':0.0,'normalizeLufs':False,'outputDir':str(poisoned_output),'preset':'fast','encoderPreference':'auto'}


def create_vyron_job(channel,idx):
    batch_id=f'ENDLUME_ROUTING_QA_{idx}_{uuid.uuid4()}'
    batch=BATCHES/batch_id
    project_dir=batch/f'ENDLUME Routing QA 10.0.15 {idx}'
    project_dir.mkdir(parents=True,exist_ok=False)
    created_batches.append(batch)
    cover,audio=make_media(project_dir,idx)
    out=(RENDER/channel).resolve()
    status=batch/'status.json';manifest=batch/'batch.json';project_id=f'qa-routing-{idx}'
    status.write_text(json.dumps({'status':'Передано ENDLUME','projects':[{'projectId':project_id,'renderStatus':'Waiting','outputFile':None,'duration':None,'fileSize':None,'error':None}]},ensure_ascii=False,indent=2),encoding='utf-8')
    manifest.write_text(json.dumps({'source':'VYRON Production Manager 10.0.15 QA','batchId':batch_id,'channelId':f'qa-channel-{idx}','channelName':channel,'projectCount':1,'rootPath':str(batch.resolve()),'outputDir':str(out),'statusPath':str(status.resolve()),'projects':[{'projectId':project_id,'folderPath':str(project_dir.resolve()),'tracks':[{'path':str(audio.resolve())}]}]},ensure_ascii=False,indent=2),encoding='utf-8')
    return {
      'project':{'id':project_id,'name':f'ENDLUME Routing QA 10.0.15 {idx}','path':str(project_dir.resolve()),'media':[str(cover.resolve())],'audio':[str(audio.resolve())],'valid':True,'error':None,'anchors':None,'selectedEffectId':'__none__','selectedEffectIds':['__none__'],'outputDir':str(out),'outputSource':'vyron','vyronManifestPath':str(manifest.resolve()),'vyronChannelName':channel},
      # Exact regression poison: shared render settings point to the project inside Batches.
      'settings':settings(project_dir.resolve()),'effects':[],'subscribes':[],'ambient':None,'ambientSettings':{'volumePct':18.0,'bassDb':0.0,'midDb':0.0,'trebleDb':0.0}
    }


def invoke(jobs,label,require_vyron_diagnostics=True):
    fixture=run_root/f'{label}-jobs.json';result=run_root/f'{label}-result.json'
    fixture.write_text(json.dumps({'jobs':jobs},ensure_ascii=False,indent=2),encoding='utf-8')
    env=os.environ.copy();env.update({'ENDLUME_E2E_RENDER_JOB':str(fixture),'ENDLUME_E2E_RESULT':str(result),'RUST_BACKTRACE':'1'})
    started=time.perf_counter();p=run([APP],env=env,timeout=360,check=False);wall=time.perf_counter()-started
    (run_root/f'{label}-stdout.log').write_text(p.stdout or '',encoding='utf-8');(run_root/f'{label}-stderr.log').write_text(p.stderr or '',encoding='utf-8')
    assert p.returncode==0,(label,p.returncode,p.stderr[-12000:])
    data=json.loads(result.read_text(encoding='utf-8'));assert data.get('status')=='passed',data
    stderr=p.stderr or ''
    if require_vyron_diagnostics:
        for token in ('VYRON ROOT=','CHANNEL=','PROJECT DIRECTORY=','BATCH DIRECTORY=','FINAL RENDER DIRECTORY=','FINAL OUTPUT FILE='):
            assert token in stderr,(label,token,stderr[-12000:])
    return data,wall,stderr


def media_files(path):
    return sorted([p.resolve() for p in path.rglob('*') if p.is_file() and p.suffix.lower() in ('.mp4','.mov')])

jobs=[create_vyron_job(channel,i+1) for i,channel in enumerate(CHANNELS)]
first,first_wall,_=invoke(jobs,'first-process')
rows={r['id']:r for r in first['results']};assert set(rows)=={j['project']['id'] for j in jobs},rows.keys()
channel_results=[]
for job in jobs:
    pid=job['project']['id'];channel=job['project']['vyronChannelName'];expected=(RENDER/channel).resolve();output=Path(rows[pid]['outputPath']).resolve()
    assert output.is_file() and output.stat().st_size>1024,output
    assert output.parent==expected,(pid,output,expected)
    assert not output.is_relative_to(BATCHES.resolve()),(pid,output)
    meta=json.loads(run([FFPROBE,'-v','error','-show_entries','stream=codec_type,codec_name,width,height,avg_frame_rate:format=duration,size','-of','json',output]).stdout)
    v=next(x for x in meta['streams'] if x.get('codec_type')=='video');a=next(x for x in meta['streams'] if x.get('codec_type')=='audio')
    assert (v.get('width'),v.get('height'),v.get('avg_frame_rate'))==(1920,1080,'60/1'),v
    created_outputs.append(output)
    channel_results.append({'channel':channel,'outputPath':str(output),'bytes':output.stat().st_size,'videoCodec':v.get('codec_name'),'audioCodec':a.get('codec_name'),'duration':float(meta['format']['duration'])})

qa_batch_roots=[p.resolve() for p in created_batches]
leaked=[str(p) for p in media_files(BATCHES) if any(p.is_relative_to(root) for root in qa_batch_roots)]
assert not leaked,leaked

# A second executable process is a real ENDLUME restart boundary.
restart_job=jobs[0];first_output=Path(rows[restart_job['project']['id']]['outputPath']).resolve()
restart,restart_wall,_=invoke([restart_job],'second-process-restart')
restart_output=Path(restart['results'][0]['outputPath']).resolve()
assert restart_output.parent==(RENDER/restart_job['project']['vyronChannelName']).resolve(),restart_output
assert restart_output==first_output,(restart_output,first_output)
assert not restart_output.is_relative_to(BATCHES.resolve()),restart_output
matching=[p for p in (RENDER/restart_job['project']['vyronChannelName']).iterdir() if p.is_file() and p.stem==restart_output.stem and p.suffix.lower() in ('.mp4','.mov')]
assert len(matching)==1,matching

# Standalone ENDLUME contract must remain unchanged.
standalone_root=run_root/'standalone';project_dir=standalone_root/'project';output_dir=standalone_root/'output';project_dir.mkdir(parents=True);output_dir.mkdir(parents=True)
cover,audio=make_media(project_dir,9)
standalone_job={'project':{'id':'qa-standalone','name':'ENDLUME Routing QA Standalone','path':str(project_dir),'media':[str(cover)],'audio':[str(audio)],'valid':True,'error':None,'anchors':None,'selectedEffectId':'__none__','selectedEffectIds':['__none__'],'outputDir':None,'outputSource':None,'vyronManifestPath':None,'vyronChannelName':None},'settings':settings(output_dir),'effects':[],'subscribes':[],'ambient':None,'ambientSettings':{'volumePct':18.0,'bassDb':0.0,'midDb':0.0,'trebleDb':0.0}}
standalone,standalone_wall,_=invoke([standalone_job],'standalone',require_vyron_diagnostics=False)
standalone_output=Path(standalone['results'][0]['outputPath']).resolve();assert standalone_output.parent==output_dir.resolve(),standalone_output

leaked=[str(p) for p in media_files(BATCHES) if any(p.is_relative_to(root) for root in qa_batch_roots)];assert not leaked,leaked
report={'status':'GREEN','externalVolume':str(EXTERNAL_VOLUME),'vyronRoot':str(VYRON),'batchesRoot':str(BATCHES.resolve()),'renderRoot':str(RENDER.resolve()),'channels':channel_results,'firstProcessWallSeconds':first_wall,'restartWallSeconds':restart_wall,'standaloneWallSeconds':standalone_wall,'batchOutputLeak':False,'restartSameOutputFile':restart_output==first_output,'duplicateFinalMedia':False,'standaloneOutput':str(standalone_output),'standaloneExpectedDirectory':str(output_dir.resolve()),'diagnosticsPresent':True,'vyronDiscoveryContractPaths':[str((RENDER/c).resolve()) for c in CHANNELS],'note':'Application-level VYRON auto-discovery is verified separately; this gate proves the exact Render/<channel> filesystem contract.'}
REPORT.parent.mkdir(parents=True,exist_ok=True);REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'PHYSICAL_VYRON_ROOT={VYRON}')
print('VYRON_RENDER_DESTINATION=PASS')
print('BATCH_OUTPUT_LEAK=PASS')
print('CHANNEL_ROUTING=PASS')
print('EXTERNAL_DISK_ROUTING=PASS')
print('RESTART_PERSISTENCE=PASS')
print('NO_DUPLICATE_FINAL_MEDIA=PASS')
print('STANDALONE_ENDLUME_REGRESSION=PASS')
print('VYRON_DISCOVERY_PATH_CONTRACT=PASS')
for batch in created_batches: shutil.rmtree(batch,ignore_errors=True)
