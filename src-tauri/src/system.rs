use serde_json::{json,Value};
use sysinfo::Disks;

#[cfg(target_os="macos")]
use std::{collections::HashSet,fs,path::{Path,PathBuf},process::Command};

#[cfg(target_os="macos")]
const ENDLUME_BUNDLE_ID:&str="studio.endlume.desktop";
#[cfg(target_os="macos")]
const ENDLUME_APP_NAME:&str="ENDLUME Studio.app";
#[cfg(target_os="macos")]
const ENDLUME_CANONICAL_PATH:&str="/Applications/ENDLUME Studio.app";

#[tauri::command]
pub fn power_status()->Value{
  #[cfg(target_os="macos")]
  {
    let out=std::process::Command::new("/usr/bin/pmset").args(["-g","batt"]).output();
    if let Ok(out)=out{
      let text=String::from_utf8_lossy(&out.stdout).to_string();
      let on_battery=text.to_lowercase().contains("battery power");
      let percent=text.split_whitespace().find_map(|x|x.trim_matches(|c:char|!c.is_ascii_digit()&&c!='%').strip_suffix('%').and_then(|n|n.parse::<u32>().ok()));
      return json!({"supported":true,"onBattery":on_battery,"percent":percent});
    }
    return json!({"supported":true,"onBattery":false,"percent":null});
  }
  #[cfg(not(target_os="macos"))]
  { json!({"supported":false,"onBattery":false,"percent":null}) }
}

#[tauri::command]
pub fn disk_status(path:Option<String>)->Value{
  let disks=Disks::new_with_refreshed_list();
  let requested=path.filter(|p|!p.trim().is_empty()).map(std::path::PathBuf::from).unwrap_or_else(||std::env::current_dir().unwrap_or_else(|_|std::path::PathBuf::from("/")));
  let best=disks.list().iter().filter(|d|requested.starts_with(d.mount_point())).max_by_key(|d|d.mount_point().as_os_str().len()).or_else(||disks.list().iter().max_by_key(|d|d.total_space()));
  if let Some(d)=best{
    let total=d.total_space();let free=d.available_space();let used=total.saturating_sub(free);
    return json!({"totalBytes":total,"freeBytes":free,"usedBytes":used,"mount":d.mount_point().to_string_lossy()});
  }
  json!({"totalBytes":0,"freeBytes":0,"usedBytes":0,"mount":""})
}

#[cfg(target_os="macos")]
fn current_app_bundle()->Option<PathBuf>{
  let exe=std::env::current_exe().ok()?;
  exe.ancestors().find(|p|p.extension().and_then(|x|x.to_str()).map(|x|x.eq_ignore_ascii_case("app")).unwrap_or(false)).map(Path::to_path_buf)
}

#[cfg(target_os="macos")]
fn canon(path:&Path)->PathBuf{fs::canonicalize(path).unwrap_or_else(|_|path.to_path_buf())}

#[cfg(target_os="macos")]
fn app_name(path:&Path)->String{path.file_name().and_then(|x|x.to_str()).unwrap_or_default().to_string()}

#[cfg(target_os="macos")]
fn canonical_name(path:&Path)->bool{app_name(path)==ENDLUME_APP_NAME}

#[cfg(target_os="macos")]
fn canonical_install(path:&Path)->bool{canon(path)==canon(Path::new(ENDLUME_CANONICAL_PATH))}

#[cfg(target_os="macos")]
fn plist_value(bundle:&Path,key:&str)->Option<String>{
  let info=bundle.join("Contents/Info.plist");
  let out=Command::new("/usr/bin/plutil").args(["-extract",key,"raw","-o","-"]).arg(info).output().ok()?;
  if !out.status.success(){return None}
  let value=String::from_utf8_lossy(&out.stdout).trim().to_string();
  if value.is_empty(){None}else{Some(value)}
}

#[cfg(target_os="macos")]
fn version_parts(value:&str)->Vec<u64>{
  value.split(|c:char|!c.is_ascii_digit()).filter(|x|!x.is_empty()).filter_map(|x|x.parse::<u64>().ok()).collect()
}

#[cfg(target_os="macos")]
fn version_cmp(a:&str,b:&str)->std::cmp::Ordering{
  let av=version_parts(a);let bv=version_parts(b);let n=av.len().max(bv.len());
  for i in 0..n{let x=*av.get(i).unwrap_or(&0);let y=*bv.get(i).unwrap_or(&0);let o=x.cmp(&y);if o!=std::cmp::Ordering::Equal{return o}}
  std::cmp::Ordering::Equal
}

#[cfg(target_os="macos")]
fn discover_endlume_apps(current:&Path)->Vec<PathBuf>{
  let mut found:HashSet<PathBuf>=HashSet::new();
  found.insert(current.to_path_buf());
  if let Ok(out)=Command::new("/usr/bin/mdfind").arg(format!("kMDItemCFBundleIdentifier == '{}'",ENDLUME_BUNDLE_ID)).output(){
    if out.status.success(){
      for line in String::from_utf8_lossy(&out.stdout).lines(){let p=PathBuf::from(line.trim());if p.extension().and_then(|x|x.to_str()).map(|x|x.eq_ignore_ascii_case("app")).unwrap_or(false){found.insert(p);}}
    }
  }
  let home=std::env::var_os("HOME").map(PathBuf::from);
  let mut roots=vec![PathBuf::from("/Applications")];
  if let Some(h)=home{roots.push(h.join("Applications"));roots.push(h.join("Desktop"));roots.push(h.join("Downloads"));}
  if let Some(parent)=current.parent(){roots.push(parent.to_path_buf());}
  for root in roots{
    if let Ok(rd)=fs::read_dir(root){for e in rd.flatten(){let p=e.path();if p.extension().and_then(|x|x.to_str()).map(|x|x.eq_ignore_ascii_case("app")).unwrap_or(false){found.insert(p);}}}
  }
  let mut apps=found.into_iter().filter(|p|plist_value(p,"CFBundleIdentifier").as_deref()==Some(ENDLUME_BUNDLE_ID)).collect::<Vec<_>>();
  apps.sort();apps
}

#[cfg(target_os="macos")]
fn privileged_remove(path:&Path)->Result<(),String>{
  let script=r#"on run argv
set targetPath to item 1 of argv
do shell script "/bin/rm -rf " & quoted form of targetPath with administrator privileges
end run"#;
  let out=Command::new("/usr/bin/osascript").args(["-e",script]).arg(path.to_string_lossy().as_ref()).output().map_err(|e|e.to_string())?;
  if out.status.success(){Ok(())}else{Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}
}

#[cfg(target_os="macos")]
fn privileged_move(from:&Path,to:&Path)->Result<(),String>{
  let script=r#"on run argv
set sourcePath to item 1 of argv
set targetPath to item 2 of argv
do shell script "/bin/mv " & quoted form of sourcePath & " " & quoted form of targetPath with administrator privileges
end run"#;
  let out=Command::new("/usr/bin/osascript").args(["-e",script]).arg(from.to_string_lossy().as_ref()).arg(to.to_string_lossy().as_ref()).output().map_err(|e|e.to_string())?;
  if out.status.success(){Ok(())}else{Err(String::from_utf8_lossy(&out.stderr).trim().to_string())}
}

#[cfg(target_os="macos")]
fn launch_app(path:&Path)->Result<(),String>{
  let p=path.to_string_lossy().into_owned();
  Command::new("/bin/sh").arg("-c").arg("sleep 0.8; /usr/bin/open -n \"$1\"").arg("endlume-relaunch").arg(p).spawn().map(|_|()).map_err(|e|e.to_string())
}

#[tauri::command]
pub fn cleanup_duplicate_apps(aggressive:bool)->Value{
  #[cfg(target_os="macos")]
  {
    let Some(current_raw)=current_app_bundle() else{return json!({"supported":true,"singleApp":false,"canonicalName":false,"canonicalInstall":false,"error":"Не удалось определить текущий ENDLUME.app"})};
    let current=canon(&current_raw);let current_version=plist_value(&current_raw,"CFBundleShortVersionString").unwrap_or_default();
    let current_in_applications=current.starts_with(Path::new("/Applications"));
    let current_is_canonical=canonical_install(&current);
    let apps=discover_endlume_apps(&current_raw);let mut removed=Vec::<String>::new();let mut failed=Vec::<Value>::new();let mut skipped=Vec::<Value>::new();let mut valid=Vec::<String>::new();
    for raw in apps{
      let p=canon(&raw);valid.push(raw.to_string_lossy().into_owned());
      if p==current{continue}
      if p.starts_with(Path::new("/Volumes")){skipped.push(json!({"path":raw,"reason":"mounted-volume"}));continue}
      let candidate_version=plist_value(&raw,"CFBundleShortVersionString").unwrap_or_default();
      if !candidate_version.is_empty()&&!current_version.is_empty()&&version_cmp(&candidate_version,&current_version)==std::cmp::Ordering::Greater{
        skipped.push(json!({"path":raw,"reason":"newer-version","version":candidate_version}));continue
      }
      if !current_is_canonical&&canonical_install(&p){
        skipped.push(json!({"path":raw,"reason":"canonical-applications-copy","version":candidate_version}));continue
      }
      match fs::remove_dir_all(&raw){
        Ok(_)=>removed.push(raw.to_string_lossy().into_owned()),
        Err(e) if aggressive=>match privileged_remove(&raw){Ok(_)=>removed.push(raw.to_string_lossy().into_owned()),Err(admin)=>failed.push(json!({"path":raw,"error":format!("{}; admin: {}",e,admin)}))},
        Err(e)=>failed.push(json!({"path":raw,"error":e.to_string()})),
      }
    }
    let remaining=discover_endlume_apps(&current_raw).into_iter().filter(|p|!canon(p).starts_with(Path::new("/Volumes"))).map(|p|p.to_string_lossy().into_owned()).collect::<Vec<_>>();
    return json!({
      "supported":true,
      "bundleId":ENDLUME_BUNDLE_ID,
      "currentPath":current_raw,
      "currentName":app_name(&current),
      "canonicalName":canonical_name(&current),
      "canonicalInstall":current_is_canonical,
      "canonicalPath":ENDLUME_CANONICAL_PATH,
      "currentVersion":current_version,
      "currentInApplications":current_in_applications,
      "found":valid,
      "removed":removed,
      "failed":failed,
      "skipped":skipped,
      "remaining":remaining,
      "singleApp":remaining.len()<=1
    });
  }
  #[cfg(not(target_os="macos"))]
  {let _=aggressive;json!({"supported":false,"singleApp":true,"canonicalName":true,"canonicalInstall":true})}
}

#[tauri::command]
pub fn normalize_current_app_name(app:tauri::AppHandle)->Result<Value,String>{
  #[cfg(target_os="macos")]
  {
    let current=current_app_bundle().ok_or("Не удалось определить текущий ENDLUME.app")?;
    if current.starts_with(Path::new("/Volumes")){return Ok(json!({"supported":true,"renamed":false,"canonicalName":false,"canonicalInstall":false,"reason":"mounted-volume","currentPath":current}));}
    let target=PathBuf::from(ENDLUME_CANONICAL_PATH);
    if canonical_install(&current){return Ok(json!({"supported":true,"renamed":false,"canonicalName":true,"canonicalInstall":true,"currentPath":current}));}

    let current_version=plist_value(&current,"CFBundleShortVersionString").unwrap_or_default();
    if target.exists(){
      let target_id=plist_value(&target,"CFBundleIdentifier");
      if target_id.as_deref()!=Some(ENDLUME_BUNDLE_ID){return Err(format!("Файл '{}' уже существует и не является ENDLUME Studio.",target.display()))}
      let target_version=plist_value(&target,"CFBundleShortVersionString").unwrap_or_default();
      if !target_version.is_empty()&&!current_version.is_empty()&&version_cmp(&target_version,&current_version)==std::cmp::Ordering::Greater{
        launch_app(&target).map_err(|e|format!("Не удалось запустить более новую ENDLUME Studio: {e}"))?;
        let response=json!({"supported":true,"renamed":false,"canonicalName":true,"canonicalInstall":true,"selectedExisting":true,"currentPath":target,"version":target_version});
        app.exit(0);
        return Ok(response);
      }
      if let Err(e)=fs::remove_dir_all(&target){privileged_remove(&target).map_err(|admin|format!("Не удалось удалить старую каноническую копию: {e}; {admin}"))?;}
    }

    if let Some(parent)=target.parent(){if !parent.exists(){fs::create_dir_all(parent).map_err(|e|format!("Не удалось подготовить /Applications: {e}"))?;}}
    if let Err(e)=fs::rename(&current,&target){privileged_move(&current,&target).map_err(|admin|format!("Не удалось перенести ENDLUME Studio в /Applications: {e}; {admin}"))?;}
    launch_app(&target).map_err(|e|format!("Приложение перенесено, но не удалось перезапустить ENDLUME: {e}"))?;
    let response=json!({"supported":true,"renamed":true,"canonicalName":true,"canonicalInstall":true,"previousPath":current,"currentPath":target});
    app.exit(0);
    return Ok(response);
  }
  #[cfg(not(target_os="macos"))]
  {let _=app;Ok(json!({"supported":false,"renamed":false,"canonicalName":true,"canonicalInstall":true}))}
}

fn ensure_exists(path:&str)->Result<(),String>{
  if std::path::Path::new(path).exists(){Ok(())}else{Err(format!("Файл не найден: {path}"))}
}

#[tauri::command]
pub fn open_result_path(path:String)->Result<(),String>{
  ensure_exists(&path)?;
  #[cfg(target_os="macos")]
  let result=std::process::Command::new("/usr/bin/open").arg(&path).spawn();
  #[cfg(target_os="windows")]
  let result=std::process::Command::new("explorer.exe").arg(&path).spawn();
  #[cfg(all(not(target_os="macos"),not(target_os="windows")))]
  let result=std::process::Command::new("xdg-open").arg(&path).spawn();
  result.map(|_|()).map_err(|e|format!("Не удалось открыть видео: {e}"))
}

#[tauri::command]
pub fn reveal_result_path(path:String)->Result<(),String>{
  ensure_exists(&path)?;
  #[cfg(target_os="macos")]
  let result=std::process::Command::new("/usr/bin/open").arg("-R").arg(&path).spawn();
  #[cfg(target_os="windows")]
  let result=std::process::Command::new("explorer.exe").arg(format!("/select,{path}")).spawn();
  #[cfg(all(not(target_os="macos"),not(target_os="windows")))]
  let result={let parent=std::path::Path::new(&path).parent().unwrap_or(std::path::Path::new(&path));std::process::Command::new("xdg-open").arg(parent).spawn()};
  result.map(|_|()).map_err(|e|format!("Не удалось открыть папку результата: {e}"))
}
