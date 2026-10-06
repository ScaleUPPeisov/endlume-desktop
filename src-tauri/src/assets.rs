use sha2::{Digest,Sha256};
use std::{collections::HashSet,fs,io::Read,path::{Path,PathBuf},time::UNIX_EPOCH};
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

fn usable_asset(path:&Path)->bool{
  path.is_file()&&!is_macos_sidecar(path)&&!has_appledouble_magic(path)&&fs::metadata(path).map(|m|m.len()>0).unwrap_or(false)
}

fn managed_root(app:&AppHandle,kind:&str)->Result<PathBuf,String>{
  let root=app.path().app_data_dir().map_err(|e|e.to_string())?.join("library-assets").join(safe_kind(kind));
  fs::create_dir_all(&root).map_err(|e|format!("Не удалось создать библиотеку ENDLUME: {e}"))?;
  Ok(root)
}

fn push_unique_candidate(candidates:&mut Vec<PathBuf>,seen:&mut HashSet<PathBuf>,candidate:PathBuf){
  if !usable_asset(&candidate){return}
  let canonical=fs::canonicalize(&candidate).unwrap_or(candidate);
  if seen.insert(canonical.clone()){candidates.push(canonical);}
}

/// Recover only by exact managed filename. ENDLUME never guesses by display name,
/// extension, ordering, or "first available" asset because that could substitute
/// a different visual effect for the user's selected preset.
pub fn repair_missing_managed_asset(app:&AppHandle,source:&str,kind:&str)->Result<Option<String>,String>{
  let stale=PathBuf::from(source);
  let Some(file_name)=stale.file_name() else{return Ok(None)};

  let root=managed_root(app,kind)?;
  let mut candidates=Vec::<PathBuf>::new();
  let mut seen=HashSet::<PathBuf>::new();

  // Current ENDLUME managed library path.
  push_unique_candidate(&mut candidates,&mut seen,root.join(file_name));

  // Previous ENDLUME application-support roots. This is intentionally shallow:
  // <Application Support>/<old-app-id>/library-assets/<kind>/<exact managed filename>.
  if let Ok(app_data)=app.path().app_data_dir(){
    if let Some(support_root)=app_data.parent(){
      if let Ok(entries)=fs::read_dir(support_root){
        for entry in entries.flatten(){
          let base=entry.path();
          if !base.is_dir(){continue}
          push_unique_candidate(&mut candidates,&mut seen,base.join("library-assets").join(safe_kind(kind)).join(file_name));
        }
      }
    }
  }

  // Future/packaged-resource compatible lookup. Current 10.0.11 bundle may not
  // contain these assets, but if a resource with the exact managed filename is
  // shipped later the resolver remains deterministic and does not depend on repo paths.
  if let Ok(resource_root)=app.path().resource_dir(){
    push_unique_candidate(&mut candidates,&mut seen,resource_root.join("library-assets").join(safe_kind(kind)).join(file_name));
    push_unique_candidate(&mut candidates,&mut seen,resource_root.join(safe_kind(kind)).join(file_name));
  }

  match candidates.len(){
    0=>Ok(None),
    1=>Ok(Some(candidates.remove(0).to_string_lossy().into_owned())),
    n=>Err(format!("Найдено {n} разных файлов с точным managed-именем '{}'; ENDLUME не будет угадывать нужный эффект.",file_name.to_string_lossy()))
  }
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
