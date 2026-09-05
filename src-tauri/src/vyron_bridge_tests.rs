use crate::vyron_bridge::{load_vyron_batch_manifest,report_vyron_render,resolve_vyron_manifest_for_request,VyronBatchRequest};
use serde_json::json;
use std::{fs,path::PathBuf};
use uuid::Uuid;

fn fixture()->(PathBuf,PathBuf,PathBuf){
  let base=std::env::temp_dir().join(format!("endlume-vyron-{}",Uuid::new_v4()));
  let root=base.join("NEON_BATCH_TEST");let project=root.join("001");let output=root.join("output");
  fs::create_dir_all(&project).unwrap();fs::create_dir_all(&output).unwrap();
  fs::write(project.join("image.jpg"),b"image").unwrap();fs::write(project.join("track_001.mp3"),b"audio").unwrap();
  let status=root.join("status.json");
  fs::write(&status,serde_json::to_vec_pretty(&json!({"status":"Передано ENDLUME","projects":[{"projectId":"001","renderStatus":"Waiting","outputFile":null,"duration":null,"fileSize":null,"error":null}]})).unwrap()).unwrap();
  let manifest=root.join("batch.json");
  fs::write(&manifest,serde_json::to_vec_pretty(&json!({
    "source":"VYRON Production Manager 1.0.4","batchId":"NEON_BATCH_TEST","channelId":"channel-neon","channelName":"NEON","projectCount":1,
    "rootPath":root.to_string_lossy(),"outputDir":output.to_string_lossy(),"statusPath":status.to_string_lossy(),
    "projects":[{"projectId":"001","folderPath":project.to_string_lossy(),"tracks":[{"path":project.join("track_001.mp3").to_string_lossy()}]}]
  })).unwrap()).unwrap();
  (base,manifest,status)
}

#[test]
fn vyron_manifest_import_and_status_roundtrip(){
  let(base,manifest,status)=fixture();
  let info=load_vyron_batch_manifest(manifest.to_string_lossy().into_owned()).unwrap();
  assert_eq!(info.channel_name,"NEON");assert_eq!(info.project_count,1);assert_eq!(info.tracks_assigned,1);assert_eq!(info.project_paths.len(),1);
  report_vyron_render(info.manifest_path.clone(),info.project_paths[0].clone(),"Rendering".into(),None,None,None,None).unwrap();
  let mid:serde_json::Value=serde_json::from_slice(&fs::read(&status).unwrap()).unwrap();assert_eq!(mid["status"],"Rendering");assert_eq!(mid["projects"][0]["renderStatus"],"Rendering");
  report_vyron_render(info.manifest_path,info.project_paths[0].clone(),"Completed".into(),Some("/tmp/final.mp4".into()),Some(7200.5),Some(900_000_000),None).unwrap();
  let done:serde_json::Value=serde_json::from_slice(&fs::read(&status).unwrap()).unwrap();assert_eq!(done["status"],"Completed");assert_eq!(done["projects"][0]["outputFile"],"/tmp/final.mp4");assert_eq!(done["projects"][0]["fileSize"],900_000_000u64);
  fs::remove_dir_all(base).unwrap();
}

#[test]
fn vyron_manifest_rejects_project_outside_batch_root(){
  let(base,manifest,_)=fixture();let root=manifest.parent().unwrap().to_path_buf();let outside=base.join("outside");fs::create_dir_all(&outside).unwrap();
  let mut v:serde_json::Value=serde_json::from_slice(&fs::read(&manifest).unwrap()).unwrap();v["projects"][0]["folderPath"]=json!(outside.to_string_lossy());fs::write(&manifest,serde_json::to_vec_pretty(&v).unwrap()).unwrap();
  let err=load_vyron_batch_manifest(manifest.to_string_lossy().into_owned()).unwrap_err();assert!(err.contains("вне batch root"));
  let _=root;fs::remove_dir_all(base).unwrap();
}

#[test]
fn vyron_request_recovers_batch_json_from_wrong_filename_in_same_folder(){
  let(base,manifest,_)=fixture();let wrong=manifest.with_file_name("VYRON batch.json");
  let req=VyronBatchRequest{batch_id:"NEON_BATCH_TEST".into(),manifest_path:wrong.to_string_lossy().into_owned(),requested_at:None};
  let resolved=resolve_vyron_manifest_for_request(&req).unwrap();
  assert_eq!(PathBuf::from(resolved).canonicalize().unwrap(),manifest.canonicalize().unwrap());
  fs::remove_dir_all(base).unwrap();
}

#[test]
fn vyron_request_rejects_manifest_from_other_batch(){
  let(base,manifest,_)=fixture();
  let req=VyronBatchRequest{batch_id:"OTHER_BATCH".into(),manifest_path:manifest.to_string_lossy().into_owned(),requested_at:None};
  assert!(resolve_vyron_manifest_for_request(&req).is_err());
  fs::remove_dir_all(base).unwrap();
}
