#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def read(path:str)->str:
    return (ROOT/path).read_text(encoding='utf-8')

def write(path:str,text:str)->None:
    (ROOT/path).write_text(text,encoding='utf-8')

def one(path:str,old:str,new:str)->None:
    text=read(path)
    n=text.count(old)
    if n!=1:
        raise SystemExit(f'{path}: expected one match, got {n}: {old[:100]!r}')
    write(path,text.replace(old,new,1))

def rx(path:str,pattern:str,replacement:str)->None:
    text=read(path)
    out,n=re.subn(pattern,replacement,text,count=1,flags=re.S)
    if n!=1:
        raise SystemExit(f'{path}: expected one regex match, got {n}: {pattern[:100]}')
    write(path,out)

# Apply the primary focused patch (including deterministic duplicate-site handling).
subprocess.run([sys.executable,str(ROOT/'scripts'/'run-endlume-1014-hotfix.py')],cwd=ROOT,check=True)

# Rust scan initializer must explicitly initialize the new optional per-project
# routing metadata. Ordinary/manual projects carry None and keep existing behavior.
one('src-tauri/src/scan.rs',
    'audio:audio.into_iter().map(|x|x.to_string_lossy().into_owned()).collect(),valid:error.is_none(),error,anchors:None,selected_effect_id:None',
    'audio:audio.into_iter().map(|x|x.to_string_lossy().into_owned()).collect(),valid:error.is_none(),error,anchors:None,selected_effect_id:None,output_dir:None,output_source:None,vyron_manifest_path:None,vyron_channel_name:None')

# Keep the current VYRON outputDir as persisted recovery fallback across app
# restart. Per-project outputDir remains authoritative during enqueue, so this
# cannot mutate an already queued channel destination.
one('src/components/VyronBatchBridge.tsx',
    "const st=useApp.getState();st.setDraftProjects(valid);st.setInvalidProjects(invalid);st.setPreviewProjectPath(valid[0]?.path);st.setLastRoot(info.rootPath);st.setPage('project');",
    "const st=useApp.getState();st.setDraftProjects(valid);st.setInvalidProjects(invalid);st.setPreviewProjectPath(valid[0]?.path);st.patchSettings({outputDir:info.outputDir});st.setLastRoot(info.rootPath);st.setPage('project');")

# Invalidate latest-request-wins token when either editor unmounts. Backend work
# is independently bounded below, so closing an editor cannot later paint stale UI.
editors=read('src/pages/Editors.tsx')
needle='  const previewRequest = useRef(0);\n'
if editors.count(needle)!=2:
    raise SystemExit(f'Editors.tsx: expected two previewRequest refs, got {editors.count(needle)}')
editors=editors.replace(needle,needle+'  useEffect(()=>()=>{previewRequest.current+=1;},[]);\n')
write('src/pages/Editors.tsx',editors)

# Subscribe recovery must state whether the path existed. prepare_live_preview
# performs is_file() before decode, so a non-missing-source error implies exists=true.
one('src/pages/Editors.tsx',
    "      const message=`Subscribe media: ${latest.name}\\nОжидаемый путь: ${latest.source}\\nФайл не удалось открыть: ${String(error)}`;\n      setPreviewError(message);console.error('[preview/error]',requestId,message);",
    "      const detail=String(error);const exists=detail.includes('exists=false')?'нет':'да';\n      const message=`Subscribe media: ${latest.name}\\nОжидаемый путь: ${latest.source}\\nФайл существует: ${exists}\\nОшибка Preview: ${detail}`;\n      setPreviewError(message);console.error('[preview/error]',requestId,message);")

# No Preview subprocess is allowed to block indefinitely. The primary patch
# already bounds ffmpeg_output; extend the same contract to diagnostics, real
# frame decode and FFprobe validation.
one('src-tauri/src/live_preview.rs',
    '  let Ok(out)=cmd.args(args).output().await else{return ("0".into(),"0".into(),"unknown".into())};',
    '  let Ok(waited)=tokio::time::timeout(PREVIEW_PROCESS_TIMEOUT,cmd.args(args).output()).await else{if live_preview_diag_enabled(){eprintln!("[preview/error] ffprobe frame diagnostic timeout");}return ("0".into(),"0".into(),"unknown".into())};\n  let Ok(out)=waited else{return ("0".into(),"0".into(),"unknown".into())};')

rx('src-tauri/src/live_preview.rs',
   r'fn direct_decode_proxy_frame\(app:&AppHandle,out:&Path\)->Result<\(\),String>\{.*?\n\}\n\nasync fn decode_proxy_frame',
   '''fn direct_decode_proxy_frame(app:&AppHandle,out:&Path)->Result<(),String>{
  let ffmpeg=resolve_bundled_ffmpeg(app)?;
  let version_args=vec!["-version".to_string()];
  let (version_ok,_,version_stdout,version_stderr)=staged_process_output(&ffmpeg,&version_args)?;
  if !version_ok{return Err(format!("bundled FFmpeg -version failed: {}",String::from_utf8_lossy(&version_stderr).trim()))}
  if live_preview_diag_enabled(){
    let binding=String::from_utf8_lossy(&version_stdout);
    let first=binding.lines().next().unwrap_or("").to_string();
    eprintln!("ENDLUME_PREVIEW_FFMPEG_VERSION_GREEN path={} version={:?}",ffmpeg.display(),first);
  }
  let args=vec!["-hide_banner","-loglevel","error","-ss","0","-i",out.to_string_lossy().as_ref(),"-map","0:v:0","-frames:v","1","-f","null","-"].into_iter().map(String::from).collect::<Vec<_>>();
  let (ok,_,_,stderr)=staged_process_output(&ffmpeg,&args)?;
  if !ok{
    let err=String::from_utf8_lossy(&stderr).trim().to_string();
    return Err(if err.is_empty(){"direct bundled FFmpeg decode failed".into()}else{err})
  }
  if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_REAL_FRAME_DECODE_GREEN mode=resolved-bundled-ffmpeg path={} ffmpeg={}",out.display(),ffmpeg.display());}
  Ok(())
}

async fn decode_proxy_frame''')

rx('src-tauri/src/live_preview.rs',
   r'async fn decode_proxy_frame\(app:&AppHandle,out:&Path\)->Result<\(\),String>\{.*?\n\}\n\npub\(crate\) async fn validate_video_proxy',
   '''async fn decode_proxy_frame(app:&AppHandle,out:&Path)->Result<(),String>{
  let args=vec!["-hide_banner","-loglevel","error","-ss","0","-i",out.to_string_lossy().as_ref(),"-map","0:v:0","-frames:v","1","-f","null","-"].into_iter().map(String::from).collect::<Vec<_>>();
  match app.shell().sidecar("ffmpeg"){
    Ok(cmd)=>match tokio::time::timeout(PREVIEW_PROCESS_TIMEOUT,cmd.args(args).output()).await{
      Ok(Ok(result))=>{
        if result.status.success(){
          if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_REAL_FRAME_DECODE_GREEN mode=tauri-sidecar path={}",out.display());}
          Ok(())
        }else{
          let err=String::from_utf8_lossy(&result.stderr).trim().to_string();
          Err(if err.is_empty(){"FFmpeg frame decode failed".into()}else{err})
        }
      },
      Ok(Err(spawn_error))=>{
        if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_DECODE_DIRECT_FALLBACK reason=spawn-error error={:?} path={}",spawn_error,out.display());}
        direct_decode_proxy_frame(app,out)
      },
      Err(_)=>Err(format!("[preview/error] FFmpeg frame decode timeout after {}s",PREVIEW_PROCESS_TIMEOUT.as_secs()))
    },
    Err(resolve_error)=>{
      if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_DECODE_DIRECT_FALLBACK reason=sidecar-resolve error={:?} path={}",resolve_error,out.display());}
      direct_decode_proxy_frame(app,out)
    }
  }
}

pub(crate) async fn validate_video_proxy''')

one('src-tauri/src/live_preview.rs',
    '    let v=std::process::Command::new(&ffprobe).args(&probe_args).output()\n      .map_err(|e|format!("staged FFprobe spawn failed {}: {e}",ffprobe.display()))?;\n    (v.status.success(),v.stdout,v.stderr)',
    '    let (ok,_code,stdout,stderr)=staged_process_output(&ffprobe,&probe_args).map_err(|e|format!("staged FFprobe failed {}: {e}",ffprobe.display()))?;\n    (ok,stdout,stderr)')

one('src-tauri/src/live_preview.rs',
    '    match cmd.args(probe_args).output().await{\n      Ok(v)=>(v.status.success(),v.stdout,v.stderr),\n      Err(e)=>{\n        if let Some(decode)=decode_error{return Err(format!("proxy decode failed ({decode}); FFprobe spawn failed: {e}"))}\n        if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_FFPROBE_FALLBACK reason=spawn-error error={:?} path={}",e,out.display());}\n        return Ok(())\n      }\n    }',
    '    match tokio::time::timeout(PREVIEW_PROCESS_TIMEOUT,cmd.args(probe_args).output()).await{\n      Ok(Ok(v))=>(v.status.success(),v.stdout,v.stderr),\n      Ok(Err(e))=>{\n        if let Some(decode)=decode_error{return Err(format!("proxy decode failed ({decode}); FFprobe spawn failed: {e}"))}\n        if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_FFPROBE_FALLBACK reason=spawn-error error={:?} path={}",e,out.display());}\n        return Ok(())\n      },\n      Err(_)=>return Err(format!("[preview/error] FFprobe sidecar preview timeout after {}s",PREVIEW_PROCESS_TIMEOUT.as_secs()))\n    }')

# If a process timed out, do not stack two more codecs behind it. Ordinary fast
# codec errors still fall back exactly as before.
one('src-tauri/src/live_preview.rs',
    '  let hw_error=hw.err().unwrap_or_else(||"unknown hardware preview failure".into());\n  #[cfg(target_os="macos")]',
    '  let hw_error=hw.err().unwrap_or_else(||"unknown hardware preview failure".into());\n  if hw_error.contains("timeout after"){let _=fs::remove_file(out);return Err(hw_error)}\n  #[cfg(target_os="macos")]')
one('src-tauri/src/live_preview.rs',
    '    let sw_error=sw.err().unwrap_or_else(||"unknown libx264 preview failure".into());\n    if let Some(safe)=safe_prefix{',
    '    let sw_error=sw.err().unwrap_or_else(||"unknown libx264 preview failure".into());\n    if sw_error.contains("timeout after"){let _=fs::remove_file(out);return Err(format!("VideoToolbox Live Preview: {hw_error}; libx264: {sw_error}"))}\n    if let Some(safe)=safe_prefix{')

# Strengthen static QA for the second pass.
qa=read('scripts/qa-endlume-1014-hotfix.py')
qa=qa.replace('assert "output_dir:Option<String>" in model\n', 'assert "output_dir:Option<String>" in model\nassert "output_dir:None,output_source:None" in text("src-tauri/src/scan.rs")\nassert "patchSettings({outputDir:info.outputDir})" in bridge\nassert "FFprobe sidecar preview timeout" in live and "ffprobe frame diagnostic timeout" in live\nassert "Файл существует: ${exists}" in editors\n')
(ROOT/'scripts'/'qa-endlume-1014-hotfix.py').write_text(qa,encoding='utf-8')

print('Applied ENDLUME 10.0.14 v2 compile + bounded-preview follow-up')
