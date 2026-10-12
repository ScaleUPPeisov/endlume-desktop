#!/usr/bin/env python3
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

APP=Path(sys.argv[1]).resolve()
FFMPEG=Path(sys.argv[2]).resolve()
FFPROBE=Path(sys.argv[3]).resolve()
REPORT=Path(sys.argv[4]).resolve()
VOL=Path('/Volumes/TOSHIBA EXT')
assert APP.is_file(), APP
assert FFMPEG.is_file() and FFPROBE.is_file(), (FFMPEG,FFPROBE)
assert VOL.is_dir(), 'TOSHIBA EXT_NOT_MOUNTED'

root=VOL/'ВАЙРОН'/'ENDLUME-QA-10.0.14-routing'
src=root/'Sources'
out_a=VOL/'ВАЙРОН'/'Render'/'ENDLUME QA 10.0.14 Channel A'
out_b=VOL/'ВАЙРОН'/'Render'/'ENDLUME QA 10.0.14 Channel B'
for p in (src,out_a,out_b): p.mkdir(parents=True,exist_ok=True)
for p in (out_a,out_b):
    for f in p.glob('*.mp4'): f.unlink()

def run(args, *, env=None, timeout=180, check=True):
    p=subprocess.run([str(x) for x in args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,timeout=timeout)
    if check and p.returncode!=0:
        raise RuntimeError(f'rc={p.returncode}: {args}\n{p.stderr[-6000:]}')
    return p

def project_fixture(name, folder):
    folder.mkdir(parents=True,exist_ok=True)
    cover=folder/'обложка тест 1014.png'
    audio=folder/'трек тест 1014.mp3'
    run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=0x182033:s=1920x1080','-frames:v','1','-y',cover])
    run([FFMPEG,'-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=12','-c:a','libmp3lame','-b:a','320k','-ar','48000','-ac','2','-y',audio])
    return cover,audio

cover_a,audio_a=project_fixture('A',src/'Канал A проект')
cover_b,audio_b=project_fixture('B',src/'Канал B проект')

def settings(out):
    return {'width':1920,'height':1080,'fps':60,'codec':'h265','bitrateMbps':30.0,'durationHours':12/3600,'durationMode':'whole-track','loopMode':'image','crossfadeSec':0.0,'normalizeLufs':False,'outputDir':str(out),'preset':'fast','encoderPreference':'auto'}

def job(pid,name,folder,cover,audio,out,channel):
    return {
      'project':{'id':pid,'name':name,'path':str(folder),'media':[str(cover)],'audio':[str(audio)],'valid':True,'error':None,'anchors':None,'selectedEffectId':'__none__','outputDir':str(out),'outputSource':'vyron','vyronManifestPath':str(root/f'{pid}-batch.json'),'vyronChannelName':channel},
      'settings':settings(out),'effects':[],'subscribes':[],'ambient':None,
      'ambientSettings':{'volumePct':18.0,'bassDb':0.0,'midDb':0.0,'trebleDb':0.0}
    }

jobs=[
  job('qa-vyron-a','ENDLUME QA VYRON A',src/'Канал A проект',cover_a,audio_a,out_a,'Channel A'),
  job('qa-vyron-b','ENDLUME QA VYRON B',src/'Канал B проект',cover_b,audio_b,out_b,'Channel B'),
]
work=Path(tempfile.mkdtemp(prefix='endlume1014-vyron-routing-'))
fixture=work/'jobs.json'; result=work/'result.json'
fixture.write_text(json.dumps({'jobs':jobs},ensure_ascii=False,indent=2),encoding='utf-8')
env=os.environ.copy(); env.update({'ENDLUME_E2E_RENDER_JOB':str(fixture),'ENDLUME_E2E_RESULT':str(result),'RUST_BACKTRACE':'1'})
started=time.perf_counter(); p=run([APP],env=env,timeout=180,check=False); wall=time.perf_counter()-started
(work/'stdout.log').write_text(p.stdout or '',encoding='utf-8'); (work/'stderr.log').write_text(p.stderr or '',encoding='utf-8')
assert p.returncode==0,(p.returncode,p.stderr[-10000:])
data=json.loads(result.read_text(encoding='utf-8')); assert data.get('status')=='passed',data
rows={r['id']:r for r in data['results']}; assert set(rows)=={'qa-vyron-a','qa-vyron-b'},rows.keys()

def validate(pid,expected,forbidden):
    q=Path(rows[pid]['outputPath']).resolve(); exp=expected.resolve(); bad=forbidden.resolve()
    assert q.is_file() and q.stat().st_size>1024,q
    assert q.parent==exp,(pid,q,exp)
    assert not q.is_relative_to(bad),(pid,q,bad)
    meta=json.loads(run([FFPROBE,'-v','error','-show_entries','stream=codec_type,codec_name,width,height,avg_frame_rate:format=duration,size','-of','json',q]).stdout)
    v=next(x for x in meta['streams'] if x.get('codec_type')=='video')
    a=next(x for x in meta['streams'] if x.get('codec_type')=='audio')
    assert (v.get('width'),v.get('height'),v.get('avg_frame_rate'))==(1920,1080,'60/1'),v
    return {'outputPath':str(q),'bytes':q.stat().st_size,'duration':float(meta['format']['duration']),'videoCodec':v.get('codec_name'),'audioCodec':a.get('codec_name'),'wallSeconds':float(rows[pid].get('wallSeconds') or 0)}

ra=validate('qa-vyron-a',out_a,out_b); rb=validate('qa-vyron-b',out_b,out_a)
report={'status':'GREEN','externalVolume':str(VOL),'sourceOnExternalDrive':True,'destinationA':str(out_a),'destinationB':str(out_b),'channelA':ra,'channelB':rb,'crossWrite':False,'appWallSeconds':wall}
REPORT.parent.mkdir(parents=True,exist_ok=True); REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('VYRON_DESTINATION_A=GREEN')
print('VYRON_DESTINATION_B=GREEN')
print('VYRON_NO_CROSS_WRITE=GREEN')
print('EXTERNAL_SOURCE_DESTINATION=GREEN')
print(f'APP_WALL_SECONDS={wall:.3f}')
