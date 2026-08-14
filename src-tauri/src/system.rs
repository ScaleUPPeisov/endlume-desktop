use serde_json::{json,Value};
use sysinfo::Disks;

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
