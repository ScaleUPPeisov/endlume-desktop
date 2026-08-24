use std::{fs,path::{Path,PathBuf}};
use tauri::{AppHandle,Manager};
use uuid::Uuid;

fn safe_ext(path:&Path)->String{
  path.extension().and_then(|x|x.to_str()).unwrap_or("bin").chars().filter(|c|c.is_ascii_alphanumeric()).collect::<String>().to_ascii_lowercase()
}

fn safe_kind(kind:&str)->&'static str{
  match kind{"subscribe"=>"subscribe","ambient"=>"ambient",_=>"effects"}
}

#[tauri::command]
pub fn import_library_asset(app:AppHandle,source:String,kind:String)->Result<String,String>{
  let src=PathBuf::from(&source);
  if !src.is_file(){return Err(format!("Выбранный файл не найден: {}",src.display()))}
  let meta=fs::metadata(&src).map_err(|e|format!("Не удалось прочитать выбранный файл: {e}"))?;
  if meta.len()==0{return Err("Выбран пустой файл".into())}

  let root=app.path().app_data_dir().map_err(|e|e.to_string())?.join("library-assets").join(safe_kind(&kind));
  fs::create_dir_all(&root).map_err(|e|format!("Не удалось создать библиотеку ENDLUME: {e}"))?;
  let ext=safe_ext(&src);
  let dst=root.join(format!("{}.{}",Uuid::new_v4(),if ext.is_empty(){"bin"}else{&ext}));
  fs::copy(&src,&dst).map_err(|e|format!("Не удалось сохранить файл внутри ENDLUME: {e}"))?;
  let copied=fs::metadata(&dst).map_err(|e|e.to_string())?;
  if copied.len()!=meta.len(){let _=fs::remove_file(&dst);return Err("Файл скопирован не полностью. Импорт отменён.".into())}
  Ok(dst.to_string_lossy().into_owned())
}
