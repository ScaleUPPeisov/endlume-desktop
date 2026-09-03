#!/usr/bin/env python3
from pathlib import Path
import json,re

VERSION='1.0.0-alpha.8.45'

def must(cond,msg):
    if not cond:
        raise SystemExit('ENDLUME 8.45: '+msg)

p=Path('src-tauri/src/render.rs')
must(p.is_file(),'src-tauri/src/render.rs missing')
r=p.read_text(encoding='utf-8')

# Keep the proven render/audio/Effects/Subscribe pipeline intact. The hotfix
# only bounds FFprobe child-process lifetime and adds finalize timing.
if 'const FFPROBE_TIMEOUT_SECS:u64=' not in r:
    marker='const CANCELLED:&str="__ENDLUME_CANCELLED__";'
    must(marker in r,'cancel marker missing')
    r=r.replace(marker,marker+'\nconst FFPROBE_TIMEOUT_SECS:u64=15;',1)

if 'async fn ffprobe_output(' not in r:
    marker='''async fn output(app:&AppHandle,name:&str,args:Vec<String>)->Result<(Vec<u8>,Vec<u8>),String>{
  let out=app.shell().sidecar(name).map_err(|e|e.to_string())?.args(args).output().await.map_err(|e|e.to_string())?;
  if !out.status.success(){return Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}
  Ok((out.stdout,out.stderr))
}
'''
    must(marker in r,'sidecar output helper changed unexpectedly')
    helper='''
async fn ffprobe_output(app:&AppHandle,args:Vec<String>)->Result<(Vec<u8>,Vec<u8>),String>{
  let cmd=app.shell().sidecar("ffprobe").map_err(|e|e.to_string())?.args(args);
  let out=tokio::time::timeout(Duration::from_secs(FFPROBE_TIMEOUT_SECS),cmd.output()).await
    .map_err(|_|format!("FFprobe verification timed out after {}s",FFPROBE_TIMEOUT_SECS))?
    .map_err(|e|e.to_string())?;
  if !out.status.success(){
    let stderr=String::from_utf8_lossy(&out.stderr).trim().to_string();
    return Err(if stderr.is_empty(){"FFprobe verification failed".into()}else{stderr})
  }
  Ok((out.stdout,out.stderr))
}
'''
    r=r.replace(marker,marker+helper,1)

# Every FFprobe call, including the optional post-verify bitrate probe, gets the
# same bounded child-process lifecycle. FFmpeg encoding itself is untouched.
r=r.replace('output(app,"ffprobe",','ffprobe_output(app,')
must('output(app,"ffprobe",' not in r,'unbounded ffprobe invocation remains')
must(r.count('ffprobe_output(app,')>=4,'expected FFprobe call sites were not patched')

# Measure the real 97% -> verified transition. Do not fake progress or move 100%
# before the real checks have completed.
old='emit_progress(app,job,started,&timer,97.0,"Финальная проверка FFprobe",&encoder,attempt,None);verify_result(app,&out,final_duration,&job.settings).await?;let result_stem='
new='emit_progress(app,job,started,&timer,97.0,"Финальная проверка FFprobe",&encoder,attempt,None);let verify_mark=Instant::now();verify_result(app,&out,final_duration,&job.settings).await?;emit_timing(app,&job.project.id,"final-verify",verify_mark.elapsed().as_secs_f64());let result_stem='
if old in r:
    r=r.replace(old,new,1)
must('"final-verify"' in r,'final verify timing missing')

# Regression locks: the speed/fidelity architecture must stay bitstream-copy at
# final mux and keep the existing Smart Size / original-audio paths.
must('"-c:v","copy","-c:a","copy"' in r,'final stream-copy mux was changed')
must('static_smart_encoder_args' in r,'Smart Size static-image pipeline missing')
must('build_long_audio' in r,'existing audio lifecycle missing')
must('verify_result(app,&out,final_duration,&job.settings).await?' in r,'real final verification missing')
p.write_text(r,encoding='utf-8')

# Version only. No settings/store/navigation/bridge migration is performed here.
p=Path('package.json'); data=json.loads(p.read_text()); data['version']=VERSION; p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
p=Path('src-tauri/tauri.conf.json'); data=json.loads(p.read_text()); data['version']=VERSION; p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
p=Path('src-tauri/Cargo.toml'); s=p.read_text(); s,n=re.subn(r'(?m)^version\s*=\s*"[^"]+"',f'version = "{VERSION}"',s,count=1); must(n==1,'Cargo package version missing'); p.write_text(s)
for rel in ['src/pages/App.tsx','src/components/ReleaseHistory.tsx']:
    q=Path(rel)
    if q.is_file():
        t=q.read_text(encoding='utf-8').replace('1.0.0-alpha.8.40',VERSION)
        q.write_text(t,encoding='utf-8')

print('ENDLUME 8.45 FFprobe/finalize hotfix applied; render/audio fidelity pipeline preserved')
