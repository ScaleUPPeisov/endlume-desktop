// Studio Bridge: local, opt-in file inbox. No network listener, OAuth or remote shell.
use crate::{model::{QueueJob,RenderSettings},queue::{self,QueueRuntime},scan};
use serde::Deserialize;
use serde_json::{json,Value};
use std::{fs,path::{Path,PathBuf},sync::Arc};
use tauri::{AppHandle,Manager};

const STUDIO: &str = "VYRON AI STUDIO";
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct BridgeRequest {
    version:u32,
    job_id:String,
    project_id:String,
    duration_minutes:u32,
    #[serde(default)] fps:Option<u32>,
    #[serde(default)] codec:Option<String>
}
fn valid_uuid(s:&str)->bool { uuid::Uuid::parse_str(s).is_ok() && s.len()==36 }
fn workspace()->Result<PathBuf,String>{
    let home=std::env::var_os("HOME").ok_or("Не указан HOME")?;
    let root=PathBuf::from(home).join("Movies").join(STUDIO);
    fs::create_dir_all(&root).map_err(|e|e.to_string())?;
    root.canonicalize().map_err(|e|e.to_string())
}
fn dirs(root:&Path)->Result<(PathBuf,PathBuf,PathBuf,PathBuf),String>{
    let inbox=root.join("Bridge").join("Inbox");
    let receipts=root.join("Bridge").join("Results");
    let projects=root.join("Projects");
    let renders=root.join("Renders");
    for d in [&inbox,&receipts,&projects,&renders] {fs::create_dir_all(d).map_err(|e|e.to_string())?;}
    Ok((inbox,receipts,projects,renders))
}
pub(crate) fn write_receipt(id:&str,value:Value)->Result<(),String>{
    if !valid_uuid(id){return Err("Неверный UUID задачи".into());}
    let root=workspace()?;let (_inbox,receipts,_projects,_renders)=dirs(&root)?;
    let file=receipts.join(format!("{id}.json"));
    let tmp=receipts.join(format!("{id}.tmp"));
    fs::write(&tmp,serde_json::to_vec_pretty(&value).map_err(|e|e.to_string())?)
        .map_err(|e|e.to_string())?;
    fs::rename(tmp,file).map_err(|e|e.to_string())
}
async fn import_file(app:&AppHandle,runtime:Arc<QueueRuntime>,file:PathBuf)->Result<(),String>{
    let root=workspace()?;let (_,_,projects,renders)=dirs(&root)?;
    let bytes=fs::read(&file).map_err(|e|e.to_string())?;
    if bytes.len()>16384{return Err("Задание больше 16 KiB".into());}
    let spec:BridgeRequest=serde_json::from_slice(&bytes).map_err(|e|e.to_string())?;
    if spec.version!=1||!valid_uuid(&spec.job_id)||!valid_uuid(&spec.project_id){
        return Err("Некорректный ID или версия задания".into())
    }
    if spec.duration_minutes<1||spec.duration_minutes>240 {return Err("Длительность вне диапазона".into());}
    let input=projects.join(&spec.project_id);
    let canonical=input.canonicalize().map_err(|_|"Нет папки медиа для задания".to_string())?;
    if !canonical.starts_with(projects.canonicalize().map_err(|e|e.to_string())?){
        return Err("Недопустимая исходная папка".into());
    }
    let scan=scan::scan_root(canonical.to_string_lossy().into_owned()).await?;
    let project=scan.into_iter().find(|x|{
        Path::new(&x.path).canonicalize().ok()==Some(canonical.clone())
    }).ok_or("ENDLUME не обнаружил медиа в папке проекта")?;
    if !project.valid {return Err(project.error.unwrap_or("Нет медиа или аудио".into()));}
    let output_dir=renders.join(&spec.project_id);
    fs::create_dir_all(&output_dir).map_err(|e|e.to_string())?;
    let settings=RenderSettings{
        width:1920,height:1080,fps:spec.fps.unwrap_or(30).clamp(24,60),
        codec:if spec.codec.as_deref()==Some("h265"){"h265".into()}else{"h264".into()},
        bitrate_mbps:8.0,duration_hours:spec.duration_minutes as f64/60.0,
        duration_mode:"exact".into(),loop_mode:"image".into(),crossfade_sec:0.0,
        normalize_lufs:false,output_dir:output_dir.to_string_lossy().into_owned(),
        preset:"fast".into(),encoder_preference:"auto".into()
    };
    let job=QueueJob {
        project:crate::model::ProjectScanItem{id:format!("studio-{}",spec.job_id),..project},
        settings,effects:vec![],subscribes:vec![],ambient:None
    };
    queue::enqueue_bridge(app.clone(),runtime,job)?;
    write_receipt(&spec.job_id,json!({"status":"queued","job_id":spec.job_id,"engine":"ENDLUME","updated_at":chrono::Utc::now().to_rfc3339()}))
}
pub(crate) fn start(app:AppHandle){
    tauri::async_runtime::spawn(async move{
        loop{
            let root=workspace();
            if let Ok(root)=root{
                if let Ok((inbox,_,_,_))=dirs(&root){
                    // Persistent 3-second heartbeat proves the actual ENDLUME
                    // bridge process is alive, not just that the inbox exists.
                    let heartbeat=root.join("Bridge").join("endlume-heartbeat.json");
                    let heartbeat_tmp=root.join("Bridge").join("endlume-heartbeat.tmp");
                    let heartbeat_data=json!({"engine":"ENDLUME","bridge_version":1,
                        "updated_at_ms":chrono::Utc::now().timestamp_millis()});
                    if let Ok(bytes)=serde_json::to_vec(&heartbeat_data){
                        if fs::write(&heartbeat_tmp,bytes).is_ok(){
                            let _=fs::rename(&heartbeat_tmp,&heartbeat);
                        }
                    }
                    let mut files=fs::read_dir(inbox.clone()).ok().into_iter()
                        .flatten().filter_map(Result::ok).map(|x|x.path())
                        .filter(|p|p.extension().and_then(|s|s.to_str())==Some("json"))
                        .collect::<Vec<_>>();
                    files.sort();
                    for file in files {
                        let Some(id)=file.file_stem().and_then(|s|s.to_str()).map(str::to_owned) else{continue};
                        if !valid_uuid(&id){continue;}
                        let processing=file.with_extension("accepted");
                        if fs::rename(&file,&processing).is_err(){continue;}
                        let runtime=app.state::<Arc<QueueRuntime>>().inner().clone();
                        if let Err(error)=import_file(&app,runtime,processing.clone()).await {
                            let _=write_receipt(&id,json!({"status":"error","job_id":id,"error":error,"engine":"ENDLUME"}));
                            let _=fs::rename(&processing,processing.with_extension("rejected"));
                        }
                    }
                }
            }
            tokio::time::sleep(std::time::Duration::from_secs(3)).await;
        }
    });
}
#[cfg(test)] mod tests{
    use super::*;
    #[test] fn strict_identifiers(){
      assert!(valid_uuid("123e4567-e89b-42d3-a456-426614174000"));
      assert!(!valid_uuid("../../etc/passwd"));
      assert!(!valid_uuid("123e4567-e89b-42d3-a456-426614174000/other"));
    }
}
