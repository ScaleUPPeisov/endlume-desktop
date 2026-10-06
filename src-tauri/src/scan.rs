use crate::model::ProjectScanItem;
use std::{fs::File,io::Read,path::{Path,PathBuf}};
use uuid::Uuid;
use walkdir::WalkDir;

const IMAGE:&[&str]=&["jpg","jpeg","png","webp","bmp","tif","tiff","heic","avif"];
const VIDEO:&[&str]=&["mp4","mov","m4v","mkv","webm","avi","wmv","flv","ts","mts","m2ts","mpg","mpeg","vob","3gp"];
const AUDIO:&[&str]=&["mp3","wav","m4a","aac","flac","ogg","opus","aiff","aif","alac"];
fn ext(p:&Path)->String{p.extension().and_then(|x|x.to_str()).unwrap_or("").to_ascii_lowercase()}
fn is_macos_sidecar(p:&Path)->bool{let n=p.file_name().and_then(|x|x.to_str()).unwrap_or("");n==".DS_Store"||n.starts_with("._")||n.starts_with(".Spotlight-")||n.starts_with(".Trashes")||n.starts_with('.')}
fn has_appledouble_magic(p:&Path)->bool{let mut b=[0u8;4];File::open(p).and_then(|mut f|f.read_exact(&mut b)).is_ok()&&matches!(u32::from_be_bytes(b),0x00051607|0x00051600)}
fn rejected_macos_input(p:&Path)->bool{is_macos_sidecar(p)||has_appledouble_magic(p)}
fn natural_key(p:&PathBuf)->(u64,String){
 let s=p.file_name().and_then(|x|x.to_str()).unwrap_or("").to_lowercase();
 let digits=s.chars().skip_while(|c|!c.is_ascii_digit()).take_while(|c|c.is_ascii_digit()).collect::<String>();
 let n=digits.parse::<u64>().unwrap_or(u64::MAX);(n,s)
}
fn natural_path_key(path:&str)->Vec<(u64,String)>{
 Path::new(path).components().map(|c|{
   let s=c.as_os_str().to_string_lossy().to_lowercase();
   let digits=s.chars().skip_while(|ch|!ch.is_ascii_digit()).take_while(|ch|ch.is_ascii_digit()).collect::<String>();
   (digits.parse::<u64>().unwrap_or(u64::MAX),s)
 }).collect()
}

#[tauri::command]
pub async fn scan_root(path:String)->Result<Vec<ProjectScanItem>,String>{
 let root=PathBuf::from(&path);if !root.is_dir(){return Err(format!("Папка не существует: {path}"))}
 let mut out=Vec::new();
 for e in WalkDir::new(&root).follow_links(false).into_iter().filter_map(Result::ok).filter(|e|e.file_type().is_dir()){
   let dir=e.path();let mut media=Vec::new();let mut audio=Vec::new();
   if let Ok(rd)=std::fs::read_dir(dir){
     for f in rd.flatten(){let p=f.path();if !p.is_file()||rejected_macos_input(&p){continue}let x=ext(&p);if IMAGE.contains(&x.as_str())||VIDEO.contains(&x.as_str()){media.push(p)}else if AUDIO.contains(&x.as_str()){audio.push(p)}}
   }
   if media.is_empty()&&audio.is_empty(){continue}
   media.sort_by_key(natural_key);audio.sort_by_key(natural_key);
   let name=dir.file_name().and_then(|x|x.to_str()).unwrap_or("project").to_string();
   let error=if media.is_empty(){Some("нет изображения или видео".to_string())}else if audio.is_empty(){Some("нет песен".to_string())}else{None};
   out.push(ProjectScanItem{
     id:Uuid::new_v4().to_string(),name,path:dir.to_string_lossy().into_owned(),
     media:media.into_iter().map(|x|x.to_string_lossy().into_owned()).collect(),
     audio:audio.into_iter().map(|x|x.to_string_lossy().into_owned()).collect(),valid:error.is_none(),error,anchors:None,selected_effect_id:None
   });
 }
 out.sort_by(|a,b|natural_path_key(&a.path).cmp(&natural_path_key(&b.path)));
 Ok(out)
}
