use serde_json::{json,Value};
use sha2::{Digest,Sha256};
use std::fs;
use tauri::{AppHandle,Manager};

const OWNER_HASH:&str="4b5631d4a5b7018be7c5237994ad4ba463a4fc1df33165beab0fedc901733ef9";

fn file(app:&AppHandle)->Result<std::path::PathBuf,String>{
  let d=app.path().app_data_dir().map_err(|e|e.to_string())?;fs::create_dir_all(&d).map_err(|e|e.to_string())?;Ok(d.join("license.json"))
}
fn mask(key:&str)->String{if key.len()<9{"••••".into()}else{format!("{}••••{}",&key[..4],&key[key.len()-4..])}}

#[tauri::command]
pub fn license_status(app:AppHandle)->Value{
  file(&app).ok().and_then(|p|fs::read(&p).ok()).and_then(|b|serde_json::from_slice::<Value>(&b).ok()).unwrap_or(json!({"valid":false}))
}

#[tauri::command]
pub fn activate_license(app:AppHandle,key:String)->Result<Value,String>{
  let key=key.trim();if key.is_empty(){return Err("Введите ключ ENDLUME".into())}
  let digest=hex::encode(Sha256::digest(key.as_bytes()));
  let v=if digest==OWNER_HASH{
    json!({"valid":true,"type":"owner-lifetime","expiresAt":null,"maskedKey":mask(key),"activatedAt":chrono::Utc::now(),"offlineUntil":null})
  }else{
    return Err("Ключ не найден. В коммерческой версии месячные ключи будут проверяться сервером ENDLUME.".into())
  };
  let path=file(&app)?;let tmp=path.with_extension("tmp");fs::write(&tmp,serde_json::to_vec_pretty(&v).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;if path.exists(){let _=fs::remove_file(&path);}fs::rename(tmp,path).map_err(|e|e.to_string())?;Ok(v)
}
