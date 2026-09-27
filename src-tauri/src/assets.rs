use sha2::{Digest,Sha256};
use std::{fs,io::Read,path::{Path,PathBuf},time::UNIX_EPOCH};
use tauri::{AppHandle,Manager};

fn safe_ext(path:&Path)->String{
  path.extension().and_then(|x|x.to_str()).unwrap_or("bin").chars().filter(|c|c.is_ascii_alphanumeric()).collect::<String>().to_ascii_lowercase()
}

fn safe_kind(kind:&str)->&'static str{
  match kind{"subscribe"=>"subscribe","ambient"=>"ambient",_=>"effects"}
}

fn has_appledouble_magic(path:&Path)->bool{
  let mut b=[0u8;4];
  fs::File::open(path).and_then(|mut f|f.read_exact(&mut b)).is_ok()&&matches!(u32::from_be_bytes(b),0x00051607|0x00051600)
}
fn is_macos_sidecar(path:&Path)->bool{
  let n=path.file_name().and_then(|x|x.to_str()).unwrap_or("");
  n==".DS_Store"||n.starts_with("._")||n.starts_with(".Spotlight-")||n.starts_with(".Trashes")||n.starts_with('.')
}

fn managed_root(app:&AppHandle,kind:&str)->Result<PathBuf,String>{
  let root=app.path().app_data_dir().map_err(|e|e.to_string())?.join("library-assets").join(safe_kind(kind));
  fs::create_dir_all(&root).map_err(|e|format!("Не удалось создать библиотеку ENDLUME: {e}"))?;
  Ok(root)
}

fn fingerprint(path:&Path,meta:&fs::Metadata)->String{
  let modified=meta.modified().ok().and_then(|t|t.duration_since(UNIX_EPOCH).ok()).map(|d|d.as_nanos()).unwrap_or(0);
  let canonical=fs::canonicalize(path).unwrap_or_else(|_|path.to_path_buf());
  let mut h=Sha256::new();
  h.update(canonical.to_string_lossy().as_bytes());
  h.update(meta.len().to_le_bytes());
  h.update(modified.to_le_bytes());
  hex::encode(h.finalize())[..32].to_string()
}

pub fn ensure_managed_asset(app:&AppHandle,source:&str,kind:&str)->Result<String,String>{
  let src=PathBuf::from(source);
  if !src.is_file(){return Err(format!("Выбранный файл не найден: {}",src.display()))}
  if is_macos_sidecar(&src)||has_appledouble_magic(&src){return Err("ENDLUME не импортирует служебные AppleDouble/resource-fork файлы macOS. Выберите настоящий медиафайл.".into())}
  let meta=fs::metadata(&src).map_err(|e|format!("Не удалось прочитать выбранный файл: {e}"))?;
  if meta.len()==0{return Err("Выбран пустой файл".into())}

  let root=managed_root(app,kind)?;
  let src_canon=fs::canonicalize(&src).unwrap_or_else(|_|src.clone());
  let root_canon=fs::canonicalize(&root).unwrap_or_else(|_|root.clone());
  if src_canon.starts_with(&root_canon){return Ok(src_canon.to_string_lossy().into_owned())}

  let ext=safe_ext(&src);
  let suffix:&str=if ext.is_empty(){"bin"}else{ext.as_str()};
  let key=fingerprint(&src,&meta);
  let dst=root.join(format!("{key}.{suffix}"));
  if let Ok(existing)=fs::metadata(&dst){
    if existing.is_file()&&existing.len()==meta.len(){return Ok(dst.to_string_lossy().into_owned())}
  }

  let tmp=root.join(format!(".{key}.copying"));
  let _=fs::remove_file(&tmp);
  fs::copy(&src,&tmp).map_err(|e|format!("Не удалось сохранить файл внутри ENDLUME: {e}"))?;
  let copied=fs::metadata(&tmp).map_err(|e|e.to_string())?;
  if copied.len()!=meta.len(){let _=fs::remove_file(&tmp);return Err("Файл скопирован не полностью. Импорт отменён.".into())}
  if dst.exists(){let _=fs::remove_file(&dst);}
  fs::rename(&tmp,&dst).map_err(|e|format!("Не удалось завершить импорт файла: {e}"))?;
  Ok(dst.to_string_lossy().into_owned())
}

#[tauri::command]
pub fn import_library_asset(app:AppHandle,source:String,kind:String)->Result<String,String>{
  ensure_managed_asset(&app,&source,&kind)
}
