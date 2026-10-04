use serde::Serialize;
use sha2::{Digest,Sha256};
use std::{fs,io::Read,path::{Path,PathBuf},sync::OnceLock,time::UNIX_EPOCH};
use tauri::{AppHandle,Manager};
use tauri_plugin_shell::ShellExt;
use walkdir::WalkDir;

const IMAGE:&[&str]=&["jpg","jpeg","png","webp","bmp","tif","tiff","heic","avif"];
const VIDEO:&[&str]=&["mp4","mov","m4v","mkv","webm","avi","wmv","flv","ts","mts","m2ts","mpg","mpeg","vob","3gp"];

#[derive(Serialize)]
#[serde(rename_all="camelCase")]
pub struct LivePreviewAssets{base_path:String,base_kind:String,overlay_path:String,base_bytes:u64,overlay_bytes:u64}

fn ext(p:&Path)->String{p.extension().and_then(|x|x.to_str()).unwrap_or("").to_ascii_lowercase()}
fn is_macos_sidecar(p:&Path)->bool{let n=p.file_name().and_then(|x|x.to_str()).unwrap_or("");n==".DS_Store"||n.starts_with("._")||n.starts_with(".Spotlight-")||n.starts_with(".Trashes")||n.starts_with('.')}
fn has_appledouble_magic(p:&Path)->bool{let mut b=[0u8;4];fs::File::open(p).and_then(|mut f|f.read_exact(&mut b)).is_ok()&&matches!(u32::from_be_bytes(b),0x00051607|0x00051600)}
fn rejected_macos_input(p:&Path)->bool{is_macos_sidecar(p)||has_appledouble_magic(p)}
fn is_image(p:&Path)->bool{IMAGE.contains(&ext(p).as_str())}
fn is_media(p:&Path)->bool{is_image(p)||VIDEO.contains(&ext(p).as_str())}
fn natural_name(p:&Path)->String{p.file_name().and_then(|x|x.to_str()).unwrap_or("").to_lowercase()}
fn ready_file(p:&Path)->bool{!is_macos_sidecar(p)&&fs::metadata(p).map(|m|m.is_file()&&m.len()>1024).unwrap_or(false)}
fn live_preview_diag_enabled()->bool{cfg!(debug_assertions)||std::env::var_os("ENDLUME_PREVIEW_DIAG").is_some()}
pub(crate) async fn frame_probe_diag(app:&AppHandle,p:&Path)->(String,String,String){
  if !p.is_file(){return ("0".into(),"0".into(),"unknown".into())}
  let args=vec!["-v","error","-select_streams","v:0","-show_entries","stream=width,height,pix_fmt","-of","json",p.to_string_lossy().as_ref()].into_iter().map(String::from).collect::<Vec<_>>();
  let Ok(cmd)=app.shell().sidecar("ffprobe") else{return ("0".into(),"0".into(),"unknown".into())};
  let Ok(out)=cmd.args(args).output().await else{return ("0".into(),"0".into(),"unknown".into())};
  let Ok(v)=serde_json::from_slice::<serde_json::Value>(&out.stdout) else{return ("0".into(),"0".into(),"unknown".into())};
  let stream=v.get("streams").and_then(|x|x.as_array()).and_then(|x|x.first());
  let w=stream.and_then(|x|x.get("width")).map(|x|x.to_string()).unwrap_or_else(||"0".into());
  let h=stream.and_then(|x|x.get("height")).map(|x|x.to_string()).unwrap_or_else(||"0".into());
  let pix=stream.and_then(|x|x.get("pix_fmt")).and_then(|x|x.as_str()).unwrap_or("unknown").to_string();
  (w,h,pix)
}

fn json_positive(v:Option<&serde_json::Value>)->bool{
  v.and_then(|x|x.as_f64().or_else(||x.as_str().and_then(|s|s.parse::<f64>().ok()))).map(|x|x.is_finite()&&x>0.0).unwrap_or(false)
}
fn proxy_probe_valid(raw:&[u8])->bool{
  let Ok(v)=serde_json::from_slice::<serde_json::Value>(raw) else{return false};
  let Some(stream)=v.get("streams").and_then(|x|x.as_array()).and_then(|x|x.first()) else{return false};
  if stream.get("codec_type").and_then(|x|x.as_str())!=Some("video"){return false}
  if !json_positive(stream.get("width"))||!json_positive(stream.get("height")){return false}
  if !json_positive(stream.get("nb_read_frames")){return false}
  json_positive(v.get("format").and_then(|x|x.get("duration")))
}
fn accept_proxy_attempt(process_ok:bool,proxy_valid:bool)->bool{process_ok&&proxy_valid}

fn cache_dir(app:&AppHandle)->Result<PathBuf,String>{let dir=app.path().app_cache_dir().map_err(|e|e.to_string())?.join("live-preview-v6");fs::create_dir_all(&dir).map_err(|e|e.to_string())?;Ok(dir)}
fn fingerprint(path:&Path,seek:f64,kind:&str)->String{let meta=fs::metadata(path).ok();let size=meta.as_ref().map(|m|m.len()).unwrap_or(0);let modified=meta.as_ref().and_then(|m|m.modified().ok()).and_then(|t|t.duration_since(UNIX_EPOCH).ok()).map(|d|d.as_secs()).unwrap_or(0);let mut h=Sha256::new();h.update(format!("{}|{}|{}|{:.2}|{}",path.to_string_lossy(),size,modified,seek,kind));hex::encode(h.finalize())[..24].to_string()}
fn first_media(project:&Path)->Option<PathBuf>{let mut files=WalkDir::new(project).max_depth(3).into_iter().filter_map(Result::ok).map(|e|e.into_path()).filter(|p|p.is_file()&&!rejected_macos_input(p)&&is_media(p)&&ready_file(p)).collect::<Vec<_>>();files.sort_by(|a,b|natural_name(a).cmp(&natural_name(b)));files.into_iter().next()}


static STAGED_FFMPEG:OnceLock<Option<PathBuf>>=OnceLock::new();
static STAGED_FFPROBE:OnceLock<Option<PathBuf>>=OnceLock::new();

fn stage_packaged_tool(app:&AppHandle,name:&str)->Option<PathBuf>{
  let exe=std::env::current_exe().ok()?;
  let exe_dir=exe.parent()?;
  #[cfg(target_os="windows")]
  let source=exe_dir.join(format!("{name}.exe"));
  #[cfg(not(target_os="windows"))]
  let source=exe_dir.join(name);
  if !executable_file(&source){return None}

  let root=app.path().app_cache_dir().ok()?.join("live-preview-tools-v1");
  fs::create_dir_all(&root).ok()?;
  let source_meta=fs::metadata(&source).ok()?;
  let file_name=source.file_name()?;
  let target=root.join(file_name);
  if fs::metadata(&target).map(|m|m.is_file()&&m.len()==source_meta.len()).unwrap_or(false)&&executable_file(&target){
    if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_TOOL_STAGE name={name} mode=cache-hit source={} staged={} bytes={}",source.display(),target.display(),source_meta.len());}
    return Some(target)
  }

  let tmp=root.join(format!(".{}-{}.tmp",name,uuid::Uuid::new_v4()));
  let _=fs::remove_file(&tmp);
  let mode=if fs::hard_link(&source,&tmp).is_ok(){
    "hard-link"
  }else{
    fs::copy(&source,&tmp).ok()?;
    "copy"
  };
  #[cfg(unix)]
  {
    use std::os::unix::fs::PermissionsExt;
    let mut permissions=fs::metadata(&tmp).ok()?.permissions();
    permissions.set_mode(permissions.mode()|0o755);
    fs::set_permissions(&tmp,permissions).ok()?;
  }
  if target.exists(){let _=fs::remove_file(&target);}
  fs::rename(&tmp,&target).ok()?;
  if !executable_file(&target){let _=fs::remove_file(&target);return None}
  if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_TOOL_STAGE name={name} mode={mode} source={} staged={} bytes={}",source.display(),target.display(),source_meta.len());}
  Some(target)
}

fn staged_ffmpeg(app:&AppHandle)->Option<PathBuf>{
  STAGED_FFMPEG.get_or_init(||stage_packaged_tool(app,"ffmpeg")).clone()
}
fn staged_ffprobe(app:&AppHandle)->Option<PathBuf>{
  STAGED_FFPROBE.get_or_init(||stage_packaged_tool(app,"ffprobe")).clone()
}
fn ensure_preview_tools_staged(app:&AppHandle){
  let ffmpeg=staged_ffmpeg(app);
  let ffprobe=staged_ffprobe(app);
  if live_preview_diag_enabled(){
    eprintln!("ENDLUME_PREVIEW_TOOL_STAGE_READY ffmpeg={} ffprobe={}",
      ffmpeg.as_ref().map(|p|p.display().to_string()).unwrap_or_else(||"<sidecar-only>".into()),
      ffprobe.as_ref().map(|p|p.display().to_string()).unwrap_or_else(||"<sidecar-only>".into()));
  }
}


#[cfg(feature="e2e-render")]
fn qa_log_first_encode_sidecar(){
  static ONCE:std::sync::Once=std::sync::Once::new();
  if std::env::var_os("ENDLUME_PREVIEW_DIAG").is_none(){return}
  ONCE.call_once(||{
    let exe=std::env::current_exe().ok();
    let path=exe.as_ref().and_then(|p|p.parent()).map(|d|{
      #[cfg(target_os="windows")]
      {d.join("ffmpeg.exe")}
      #[cfg(not(target_os="windows"))]
      {d.join("ffmpeg")}
    });
    let exists=path.as_ref().map(|p|p.is_file()).unwrap_or(false);
    #[cfg(unix)]
    let executable=path.as_ref().and_then(|p|std::fs::metadata(p).ok()).map(|m|{
      use std::os::unix::fs::PermissionsExt;
      m.permissions().mode()&0o111!=0
    }).unwrap_or(false);
    #[cfg(not(unix))]
    let executable=exists;
    let resolved=path.as_ref().and_then(|p|std::fs::canonicalize(p).ok()).or(path.clone());
    let bundled=match (&exe,&resolved){
      (Some(e),Some(r))=>e.parent().map(|d|r.starts_with(d)).unwrap_or(false),
      _=>false
    };
    eprintln!("FIRST_ENCODE_EXECUTABLE_SOURCE=tauri-plugin-shell sidecar externalBin");
    eprintln!("FIRST_ENCODE_RESOLVED_PATH={}",resolved.as_ref().map(|p|p.display().to_string()).unwrap_or_else(||"<none>".into()));
    eprintln!("FIRST_ENCODE_IS_BUNDLED={}",bundled);
    eprintln!("FIRST_ENCODE_EXISTS={}",exists);
    eprintln!("FIRST_ENCODE_EXECUTABLE={}",executable);
  });
}

async fn run(app:&AppHandle,args:Vec<String>)->Result<(),String>{
  // Capture stable self-contained tool copies before the first Tauri externalBin
  // spawn. Packaged macOS E2E can resolve the first sidecar and return ENOENT on
  // later sidecar spawns; the cached executables remain addressable.
  ensure_preview_tools_staged(app);
  #[cfg(feature="e2e-render")]
  qa_log_first_encode_sidecar();
  let out=app.shell().sidecar("ffmpeg").map_err(|e|e.to_string())?.args(args).output().await.map_err(|e|e.to_string())?;
  if out.status.success(){Ok(())}else{Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}
}

fn executable_file(p:&Path)->bool{
  if !p.is_file(){return false}
  #[cfg(unix)]
  {
    use std::os::unix::fs::PermissionsExt;
    return fs::metadata(p).map(|m|m.permissions().mode()&0o111!=0).unwrap_or(false)
  }
  #[cfg(not(unix))]
  {true}
}

fn ffmpeg_candidate_name(p:&Path)->bool{
  let name=p.file_name().and_then(|x|x.to_str()).unwrap_or("").to_ascii_lowercase();
  #[cfg(target_os="windows")]
  {name=="ffmpeg.exe"||(name.starts_with("ffmpeg-")&&name.ends_with(".exe"))}
  #[cfg(not(target_os="windows"))]
  {name=="ffmpeg"||name.starts_with("ffmpeg-")}
}

fn app_bundle_root(exe:&Path)->Option<PathBuf>{
  #[cfg(target_os="macos")]
  {
    exe.ancestors().find(|p|p.extension().and_then(|x|x.to_str()).map(|x|x.eq_ignore_ascii_case("app")).unwrap_or(false)).map(Path::to_path_buf)
  }
  #[cfg(not(target_os="macos"))]
  {exe.parent().map(Path::to_path_buf)}
}

fn resolve_bundled_ffmpeg(app:&AppHandle)->Result<PathBuf,String>{
  if let Some(staged)=staged_ffmpeg(app).filter(|p|executable_file(p)){
    if live_preview_diag_enabled(){eprintln!("RESOLVED_FFMPEG_PATH={} FILE_EXISTS=true EXECUTABLE=true RESOLUTION=staged-cache",staged.display());}
    return Ok(staged)
  }
  let exe=std::env::current_exe().map_err(|e|format!("Live Preview current_exe: {e}"))?;
  let exe_dir=exe.parent().map(Path::to_path_buf).ok_or("Live Preview executable directory missing")?;
  let resource_dir=app.path().resource_dir().ok();
  let bundle=app_bundle_root(&exe);

  // In a packaged macOS app Tauri places externalBin next to the main executable:
  // Contents/MacOS/ffmpeg. Resolve that exact sibling first. This is the same path
  // used successfully by the initial sidecar encode and avoids relying on a
  // recursive bundle walk during the second-process validation pass.
  #[cfg(target_os="windows")]
  let direct_names=["ffmpeg.exe","ffmpeg-x86_64-pc-windows-msvc.exe"];
  #[cfg(not(target_os="windows"))]
  let direct_names=["ffmpeg","ffmpeg-aarch64-apple-darwin"];
  for name in direct_names{
    let candidate=exe_dir.join(name);
    if executable_file(&candidate){
      let resolved=fs::canonicalize(&candidate).unwrap_or(candidate);
      if live_preview_diag_enabled(){
        eprintln!("RESOLVED_FFMPEG_PATH={} FILE_EXISTS=true EXECUTABLE=true RESOLUTION=exact-sibling",resolved.display());
      }
      return Ok(resolved)
    }
  }

  if live_preview_diag_enabled(){
    eprintln!("ENDLUME_PREVIEW_FFMPEG_CONTEXT APP_BUNDLE_PATH={} RESOURCE_DIR={} EXECUTABLE_DIR={}",
      bundle.as_ref().map(|p|p.display().to_string()).unwrap_or_else(||"<none>".into()),
      resource_dir.as_ref().map(|p|p.display().to_string()).unwrap_or_else(||"<none>".into()),
      exe_dir.display());
  }

  let mut roots=Vec::<PathBuf>::new();
  if let Some(p)=bundle.clone(){roots.push(p);}
  if let Some(p)=resource_dir.clone(){roots.push(p);}
  roots.push(exe_dir);
  let mut seen=std::collections::HashSet::<PathBuf>::new();
  let mut candidates=Vec::<PathBuf>::new();
  for root in roots{
    if !root.exists(){continue}
    for entry in WalkDir::new(&root).max_depth(6).follow_links(false).into_iter().filter_map(Result::ok){
      let p=entry.path();
      if !ffmpeg_candidate_name(p)||!executable_file(p){continue}
      let canonical=fs::canonicalize(p).unwrap_or_else(|_|p.to_path_buf());
      if seen.insert(canonical.clone()){
        if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_FFMPEG_CANDIDATE path={} EXISTS=true EXECUTABLE=true",canonical.display());}
        candidates.push(canonical);
      }
    }
  }
  candidates.sort();
  if candidates.is_empty(){return Err("Bundled FFmpeg resolver found no executable candidate inside packaged app/resources".into())}
  if candidates.len()==1{
    let p=candidates.remove(0);
    if live_preview_diag_enabled(){eprintln!("RESOLVED_FFMPEG_PATH={} FILE_EXISTS=true EXECUTABLE=true",p.display());}
    return Ok(p)
  }
  let exact=candidates.iter().filter(|p|{
    let n=p.file_name().and_then(|x|x.to_str()).unwrap_or("");
    #[cfg(target_os="windows")]
    {n.eq_ignore_ascii_case("ffmpeg.exe")}
    #[cfg(not(target_os="windows"))]
    {n=="ffmpeg"}
  }).cloned().collect::<Vec<_>>();
  if exact.len()==1{
    let p=exact[0].clone();
    if live_preview_diag_enabled(){eprintln!("RESOLVED_FFMPEG_PATH={} FILE_EXISTS=true EXECUTABLE=true",p.display());}
    return Ok(p)
  }
  Err(format!("Bundled FFmpeg resolver is ambiguous: {}",candidates.iter().map(|p|p.display().to_string()).collect::<Vec<_>>().join(" | ")))
}

fn direct_decode_proxy_frame(app:&AppHandle,out:&Path)->Result<(),String>{
  let ffmpeg=resolve_bundled_ffmpeg(app)?;
  let version=std::process::Command::new(&ffmpeg).arg("-version").output().map_err(|e|format!("bundled FFmpeg -version spawn: {e}"))?;
  if !version.status.success(){return Err(format!("bundled FFmpeg -version failed: {}",String::from_utf8_lossy(&version.stderr).trim()))}
  if live_preview_diag_enabled(){
    let first=String::from_utf8_lossy(&version.stdout).lines().next().unwrap_or("").to_string();
    eprintln!("ENDLUME_PREVIEW_FFMPEG_VERSION_GREEN path={} version={:?}",ffmpeg.display(),first);
  }
  let result=std::process::Command::new(&ffmpeg)
    .args(["-hide_banner","-loglevel","error","-ss","0","-i"])
    .arg(out)
    .args(["-map","0:v:0","-frames:v","1","-f","null","-"])
    .output()
    .map_err(|e|format!("direct bundled FFmpeg decode spawn: {e}"))?;
  if !result.status.success(){
    let err=String::from_utf8_lossy(&result.stderr).trim().to_string();
    return Err(if err.is_empty(){"direct bundled FFmpeg decode failed".into()}else{err})
  }
  if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_REAL_FRAME_DECODE_GREEN mode=resolved-bundled-ffmpeg path={} ffmpeg={}",out.display(),ffmpeg.display());}
  Ok(())
}

async fn decode_proxy_frame(app:&AppHandle,out:&Path)->Result<(),String>{
  let args=vec!["-hide_banner","-loglevel","error","-ss","0","-i",out.to_string_lossy().as_ref(),"-map","0:v:0","-frames:v","1","-f","null","-"].into_iter().map(String::from).collect::<Vec<_>>();
  match app.shell().sidecar("ffmpeg"){
    Ok(cmd)=>match cmd.args(args).output().await{
      Ok(result)=>{
        if result.status.success(){
          if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_REAL_FRAME_DECODE_GREEN mode=tauri-sidecar path={}",out.display());}
          Ok(())
        }else{
          let err=String::from_utf8_lossy(&result.stderr).trim().to_string();
          Err(if err.is_empty(){"FFmpeg frame decode failed".into()}else{err})
        }
      },
      Err(spawn_error)=>{
        if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_DECODE_DIRECT_FALLBACK reason=spawn-error error={:?} path={}",spawn_error,out.display());}
        direct_decode_proxy_frame(app,out)
      }
    },
    Err(resolve_error)=>{
      if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_DECODE_DIRECT_FALLBACK reason=sidecar-resolve error={:?} path={}",resolve_error,out.display());}
      direct_decode_proxy_frame(app,out)
    }
  }
}

pub(crate) async fn validate_video_proxy(app:&AppHandle,out:&Path)->Result<(),String>{
  if !ready_file(out){return Err("proxy-файл отсутствует или слишком мал".into())}
  // Prefer a direct FFmpeg decode. On packaged macOS Tauri can successfully use
  // externalBin for the encode and still return ENOENT on a second ffmpeg spawn.
  // In that exact case FFprobe frame counting is the independent decode gate:
  // it must actually read >0 video frames plus valid geometry and duration.
  let decode_error=decode_proxy_frame(app,out).await.err();
  let probe_args=vec![
    "-v","error","-select_streams","v:0","-count_frames",
    "-show_entries","stream=codec_type,width,height,nb_read_frames:format=duration",
    "-of","json",out.to_string_lossy().as_ref()
  ].into_iter().map(String::from).collect::<Vec<_>>();
  let (probe_success,probe_stdout,probe_stderr)=if let Some(ffprobe)=staged_ffprobe(app).filter(|p|executable_file(p)){
    if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_FFPROBE_SOURCE=staged-cache path={}",ffprobe.display());}
    let v=std::process::Command::new(&ffprobe).args(&probe_args).output()
      .map_err(|e|format!("staged FFprobe spawn failed {}: {e}",ffprobe.display()))?;
    (v.status.success(),v.stdout,v.stderr)
  }else{
    let cmd=match app.shell().sidecar("ffprobe"){
      Ok(v)=>v,
      Err(e)=>{
        if let Some(decode)=decode_error{return Err(format!("proxy decode failed ({decode}); FFprobe sidecar unavailable: {e}"))}
        if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_FFPROBE_FALLBACK reason=sidecar-unavailable path={}",out.display());}
        return Ok(())
      }
    };
    match cmd.args(probe_args).output().await{
      Ok(v)=>(v.status.success(),v.stdout,v.stderr),
      Err(e)=>{
        if let Some(decode)=decode_error{return Err(format!("proxy decode failed ({decode}); FFprobe spawn failed: {e}"))}
        if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_FFPROBE_FALLBACK reason=spawn-error error={:?} path={}",e,out.display());}
        return Ok(())
      }
    }
  };
  if !probe_success{return Err(format!("FFprobe не принял proxy: {}",String::from_utf8_lossy(&probe_stderr).trim()))}
  if !proxy_probe_valid(&probe_stdout){return Err("FFprobe не подтвердил video stream / geometry / decoded frames / duration".into())}
  if let Some(decode)=decode_error{
    if live_preview_diag_enabled(){eprintln!("ENDLUME_PREVIEW_REAL_FRAME_DECODE_GREEN mode=ffprobe-count-frames fallback_reason={:?} path={}",decode,out.display());}
  }
  Ok(())
}

async fn proxy_attempt(app:&AppHandle,prefix:&[String],codec:Vec<String>,out:&Path)->Result<(),String>{
  let name=out.file_name().and_then(|x|x.to_str()).unwrap_or("preview.mp4");
  let tmp=out.with_file_name(format!("{name}-{}.tmp.mp4",uuid::Uuid::new_v4()));
  let mut args=prefix.to_vec();args.extend(codec);args.extend(vec!["-movflags","+faststart","-y",tmp.to_string_lossy().as_ref()].into_iter().map(String::from));
  let process=run(app,args).await;
  let validation=if process.is_ok(){validate_video_proxy(app,&tmp).await}else{Err("FFmpeg process failed".into())};
  if accept_proxy_attempt(process.is_ok(),validation.is_ok()){
    if validate_video_proxy(app,out).await.is_ok(){let _=fs::remove_file(&tmp);return Ok(())}
    let _=fs::remove_file(out);
    fs::rename(&tmp,out).map_err(|e|format!("Live Preview atomic proxy publish {}: {e}",out.display()))?;
    return Ok(())
  }
  let _=fs::remove_file(&tmp);
  let process_error=process.err().unwrap_or_else(||"FFmpeg exit=0".into());
  let validation_error=validation.err().unwrap_or_else(||"proxy validation passed".into());
  Err(format!("{process_error}; validation: {validation_error}"))
}

fn hardware_codec_args()->Vec<String>{
  #[cfg(target_os="macos")]
  {vec!["-c:v","h264_videotoolbox","-realtime","1","-q:v","72","-g","1","-bf","0","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()}
  #[cfg(not(target_os="macos"))]
  {vec!["-c:v","libx264","-preset","ultrafast","-crf","18","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()}
}
fn software_codec_args()->Vec<String>{vec!["-c:v","libx264","-preset","ultrafast","-crf","18","-g","1","-keyint_min","1","-sc_threshold","0","-bf","0","-pix_fmt","yuv420p"].into_iter().map(String::from).collect()}

async fn encode_proxy(app:&AppHandle,prefix:Vec<String>,safe_prefix:Option<Vec<String>>,out:&Path)->Result<(),String>{
  let hw=proxy_attempt(app,&prefix,hardware_codec_args(),out).await;
  if hw.is_ok(){return Ok(())}
  let hw_error=hw.err().unwrap_or_else(||"unknown hardware preview failure".into());
  #[cfg(target_os="macos")]
  {
    let sw=proxy_attempt(app,&prefix,software_codec_args(),out).await;
    if sw.is_ok(){return Ok(())}
    let sw_error=sw.err().unwrap_or_else(||"unknown libx264 preview failure".into());
    if let Some(safe)=safe_prefix{
      let safe_result=proxy_attempt(app,&safe,software_codec_args(),out).await;
      if safe_result.is_ok(){return Ok(())}
      let safe_error=safe_result.err().unwrap_or_else(||"unknown safe preview failure".into());
      let _=fs::remove_file(out);
      return Err(format!("VideoToolbox Live Preview: {hw_error}; libx264: {sw_error}; safe fps fallback: {safe_error}"))
    }
    let _=fs::remove_file(out);
    Err(format!("VideoToolbox Live Preview: {hw_error}; libx264 fallback: {sw_error}"))
  }
  #[cfg(not(target_os="macos"))]
  {
    let _=fs::remove_file(out);
    Err(hw_error)
  }
}

async fn make_base(app:&AppHandle,src:&Path,seek:f64,out:&Path)->Result<String,String>{
  if is_image(src){
    if ready_file(out){return Ok("image".into())}
    let name=out.file_name().and_then(|x|x.to_str()).unwrap_or("base.png");
    let tmp=out.with_file_name(format!("{name}-{}.tmp.png",uuid::Uuid::new_v4()));
    let args=vec!["-hide_banner","-loglevel","error","-i",src.to_string_lossy().as_ref(),"-vf","scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2","-frames:v","1","-compression_level","1","-y",tmp.to_string_lossy().as_ref()].into_iter().map(String::from).collect::<Vec<_>>();
    let output=app.shell().sidecar("ffmpeg").map_err(|e|format!("FFmpeg Live Preview недоступен: {e}"))?.args(args).output().await.map_err(|e|format!("Не удалось запустить FFmpeg Live Preview: {e}"))?;
    let stderr=String::from_utf8_lossy(&output.stderr).trim().to_string();
    let (width,height,pix_fmt)=frame_probe_diag(app,&tmp).await;
    if live_preview_diag_enabled(){
      let size=fs::metadata(&tmp).map(|m|m.len()).unwrap_or(0);
      eprintln!("ENDLUME_PREVIEW_BASE SOURCE_IMAGE={} BASE_FRAME_PATH={} BASE_FRAME_EXISTS={} BASE_FRAME_SIZE={} WIDTH={} HEIGHT={} PIX_FMT={} FFMPEG_EXIT={:?} STDERR={:?} CACHE_KEY={} TEMP_PATH={}",src.display(),out.display(),tmp.is_file(),size,width,height,pix_fmt,output.status.code(),stderr,out.file_stem().and_then(|x|x.to_str()).unwrap_or(""),tmp.display());
    }
    if !output.status.success(){let _=fs::remove_file(&tmp);return Err(if stderr.is_empty(){"Не удалось создать базовый кадр Live Preview".into()}else{stderr})}
    if !ready_file(&tmp){let _=fs::remove_file(&tmp);return Err("Не удалось создать базовый кадр Live Preview".into())}
    if ready_file(out){let _=fs::remove_file(&tmp);}else{let _=fs::remove_file(out);fs::rename(&tmp,out).map_err(|e|format!("Live Preview atomic base publish: {e}"))?;}
    Ok("image".into())
  }else{
    if validate_video_proxy(app,out).await.is_ok(){return Ok("video".into())}
    let _=fs::remove_file(out);
    let prefix=vec!["-hide_banner","-loglevel","error","-stream_loop","-1","-ss",&seek.max(0.0).to_string(),"-i",src.to_string_lossy().as_ref(),"-t","5","-an","-vf","scale=960:540:force_original_aspect_ratio=decrease,pad=960:540:(ow-iw)/2:(oh-ih)/2,fps=30"].into_iter().map(String::from).collect();
    encode_proxy(app,prefix,None,out).await?;Ok("video".into())
  }
}

async fn make_overlay(app:&AppHandle,src:&Path,seek:f64,out:&Path)->Result<(),String>{
  if validate_video_proxy(app,out).await.is_ok(){return Ok(())}
  let _=fs::remove_file(out);
  let seek_text=seek.max(0.0).to_string();
  let src_text=src.to_string_lossy().into_owned();
  let common=vec!["-hide_banner".into(),"-loglevel".into(),"error".into(),"-stream_loop".into(),"-1".into(),"-ss".into(),seek_text,"-i".into(),src_text,"-t".into(),"6".into(),"-an".into(),"-vf".into()];
  let mut prefix=common.clone();
  prefix.push("scale=640:-2:flags=fast_bilinear,minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1".into());
  let mut safe=common;
  safe.push("scale=640:-2:flags=lanczos,fps=60".into());
  encode_proxy(app,prefix,Some(safe),out).await
}

#[tauri::command]
pub async fn prepare_live_preview(app:AppHandle,project_path:String,overlay_source:String,time_sec:f64,request_id:Option<String>,preview_type:Option<String>)->Result<LivePreviewAssets,String>{
  let project=PathBuf::from(project_path);if !project.is_dir(){return Err("Сначала выберите папку проекта".into())}
  let overlay=PathBuf::from(overlay_source);if !overlay.is_file(){return Err("Не найден файл Effects/Subscribe".into())}if rejected_macos_input(&overlay){return Err("ENDLUME заблокировала служебный AppleDouble/resource-fork файл macOS. Выберите настоящий Effects/Subscribe файл.".into())}if rejected_macos_input(&overlay){return Err("ENDLUME заблокировала служебный AppleDouble/resource-fork файл macOS. Выберите настоящий Effects/Subscribe файл.".into())}
  let base=first_media(&project).ok_or("В проекте нет корректного изображения или видео")?;let dir=cache_dir(&app)?;
  // Real user Subscribe asset is still green-only at t=0. The proven first visible
  // chroma-safe frame is ~0.75s, so only Subscribe Preview gets this minimum seek.
  let overlay_seek=if preview_type.as_deref()==Some("Subscribe") && time_sec<0.75{0.75}else{time_sec};
  let base_key=fingerprint(&base,time_sec,"base");let overlay_key=fingerprint(&overlay,overlay_seek,"overlay");
  let base_out=if is_image(&base){dir.join(format!("base-{base_key}.png"))}else{dir.join(format!("base-{base_key}.mp4"))};let overlay_out=dir.join(format!("overlay-{overlay_key}.mp4"));
  let base_kind=make_base(&app,&base,time_sec,&base_out).await?;make_overlay(&app,&overlay,overlay_seek,&overlay_out).await?;
  if live_preview_diag_enabled(){
    let request=request_id.as_deref().unwrap_or("<none>");
    let kind=preview_type.as_deref().unwrap_or("Unknown");
    let base_bytes=fs::metadata(&base_out).map(|m|m.len()).unwrap_or(0);
    let overlay_bytes=fs::metadata(&overlay_out).map(|m|m.len()).unwrap_or(0);
    eprintln!("PREVIEW_REQUEST_ID={request}");
    eprintln!("PREVIEW_TYPE={kind}");
    eprintln!("SOURCE_IMAGE={}",base.display());
    eprintln!("BASE_FRAME_PATH={}",base_out.display());
    eprintln!("BASE_FRAME_EXISTS={}",base_out.is_file());
    eprintln!("BASE_FRAME_BYTES={base_bytes}");
    eprintln!("OVERLAY_PROXY_PATH={}",overlay_out.display());
    eprintln!("OVERLAY_PROXY_EXISTS={}",overlay_out.is_file());
    eprintln!("OVERLAY_PROXY_BYTES={overlay_bytes}");
    eprintln!("OVERLAY_PREVIEW_SEEK_SEC={overlay_seek}");
  }
  Ok(LivePreviewAssets{base_path:base_out.to_string_lossy().into_owned(),base_kind,overlay_path:overlay_out.to_string_lossy().into_owned(),base_bytes:fs::metadata(&base_out).map(|m|m.len()).unwrap_or(0),overlay_bytes:fs::metadata(&overlay_out).map(|m|m.len()).unwrap_or(0)})
}

#[cfg(test)]
mod tests{
  use super::*;

  #[test]
  fn hardware_success_with_valid_proxy_is_accepted(){assert!(accept_proxy_attempt(true,true));}

  #[test]
  fn hardware_exit_zero_with_invalid_proxy_requires_fallback(){assert!(!accept_proxy_attempt(true,false));}

  #[test]
  fn hardware_process_failure_requires_fallback(){assert!(!accept_proxy_attempt(false,false));}

  #[test]
  fn libx264_success_with_valid_proxy_is_accepted(){assert!(accept_proxy_attempt(true,true));}

  #[test]
  fn ffprobe_contract_requires_video_geometry_and_duration(){
    let good=br#"{"streams":[{"codec_type":"video","width":640,"height":360,"nb_read_frames":"180"}],"format":{"duration":"6.000000"}}"#;
    let no_stream=br#"{"streams":[],"format":{"duration":"6.000000"}}"#;
    let no_frames=br#"{"streams":[{"codec_type":"video","width":640,"height":360,"nb_read_frames":"0"}],"format":{"duration":"6.000000"}}"#;
    let no_duration=br#"{"streams":[{"codec_type":"video","width":640,"height":360,"nb_read_frames":"180"}],"format":{"duration":"0"}}"#;
    assert!(proxy_probe_valid(good));assert!(!proxy_probe_valid(no_stream));assert!(!proxy_probe_valid(no_frames));assert!(!proxy_probe_valid(no_duration));
  }
}
