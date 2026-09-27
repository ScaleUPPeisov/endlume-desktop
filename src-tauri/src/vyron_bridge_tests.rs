use crate::vyron_bridge::{load_vyron_batch_manifest,report_vyron_render,resolve_vyron_manifest_for_request,VyronBatchRequest};
use serde_json::json;
use std::{fs,path::PathBuf};
use uuid::Uuid;

fn fixture()->(PathBuf,PathBuf,PathBuf){
  let base=std::env::temp_dir().join(format!("endlume-vyron-{}",Uuid::new_v4()));
  let workspace=base.join("ВАЙРОН");
  let root=workspace.join("ProductionManager").join("Batches").join("NEON_BATCH_TEST");let project=root.join("001");let output=root.join("output");
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

fn request(batch_id:&str,manifest_path:String)->VyronBatchRequest{
  VyronBatchRequest{batch_id:batch_id.into(),manifest_path,requested_at:None,handoff_id:None,selected_project_ids:vec![],source_manifest_path:None,schema_version:Some(1)}
}

#[test]
fn vyron_manifest_import_and_status_roundtrip(){
  let(base,manifest,status)=fixture();
  let info=load_vyron_batch_manifest(manifest.to_string_lossy().into_owned(),None).unwrap();
  assert_eq!(info.channel_name,"NEON");assert_eq!(info.project_count,1);assert_eq!(info.tracks_assigned,1);assert_eq!(info.project_paths.len(),1);
  let expected=base.join("ВАЙРОН").join("Render").join("NEON").canonicalize().unwrap();
  assert_eq!(PathBuf::from(&info.output_dir),expected);assert!(expected.is_dir());
  report_vyron_render(info.manifest_path.clone(),info.project_paths[0].clone(),"Rendering".into(),None,None,None,None).unwrap();
  let mid:serde_json::Value=serde_json::from_slice(&fs::read(&status).unwrap()).unwrap();assert_eq!(mid["status"],"Rendering");assert_eq!(mid["projects"][0]["renderStatus"],"Rendering");
  let rendered=expected.join("NEON — Ready Videos.mp4");
  report_vyron_render(info.manifest_path,info.project_paths[0].clone(),"Completed".into(),Some(rendered.to_string_lossy().into_owned()),Some(7200.5),Some(900_000_000),None).unwrap();
  let done:serde_json::Value=serde_json::from_slice(&fs::read(&status).unwrap()).unwrap();assert_eq!(done["status"],"Completed");assert_eq!(done["projects"][0]["outputFile"],rendered.to_string_lossy().as_ref());assert_eq!(done["projects"][0]["fileSize"],900_000_000u64);
  fs::remove_dir_all(base).unwrap();
}

#[test]
fn vyron_render_library_sanitizes_channel_folder(){
  let(base,manifest,_)=fixture();
  let mut v:serde_json::Value=serde_json::from_slice(&fs::read(&manifest).unwrap()).unwrap();v["channelName"]=json!("Aegean/Afterglow: Live");fs::write(&manifest,serde_json::to_vec_pretty(&v).unwrap()).unwrap();
  let info=load_vyron_batch_manifest(manifest.to_string_lossy().into_owned(),None).unwrap();
  let expected=base.join("ВАЙРОН").join("Render").join("Aegean_Afterglow_ Live").canonicalize().unwrap();
  assert_eq!(PathBuf::from(info.output_dir),expected);assert!(expected.is_dir());
  fs::remove_dir_all(base).unwrap();
}

#[test]
fn vyron_manifest_rejects_project_outside_batch_root(){
  let(base,manifest,_)=fixture();let root=manifest.parent().unwrap().to_path_buf();let outside=base.join("outside");fs::create_dir_all(&outside).unwrap();
  let mut v:serde_json::Value=serde_json::from_slice(&fs::read(&manifest).unwrap()).unwrap();v["projects"][0]["folderPath"]=json!(outside.to_string_lossy());fs::write(&manifest,serde_json::to_vec_pretty(&v).unwrap()).unwrap();
  let err=load_vyron_batch_manifest(manifest.to_string_lossy().into_owned(),None).unwrap_err();assert!(err.contains("вне batch root"));
  let _=root;fs::remove_dir_all(base).unwrap();
}

#[test]
fn vyron_request_recovers_source_manifest_from_live_handoff_schema(){
  let(base,manifest,_)=fixture();let handoff=manifest.with_file_name(".vyron-handoff-test.json");
  fs::write(&handoff,serde_json::to_vec_pretty(&json!({
    "batchId":"NEON_BATCH_TEST","handoffId":"test","manifestPath":handoff.to_string_lossy(),"requestedAt":"2026-09-05T10:59:22Z","schemaVersion":1,
    "selectedProjectIds":["001"],"sourceManifestPath":manifest.to_string_lossy()
  })).unwrap()).unwrap();
  let req=request("NEON_BATCH_TEST",handoff.to_string_lossy().into_owned());
  let resolved=resolve_vyron_manifest_for_request(&req).unwrap();
  assert_eq!(PathBuf::from(resolved).canonicalize().unwrap(),manifest.canonicalize().unwrap());
  fs::remove_dir_all(base).unwrap();
}

#[test]
fn vyron_request_prefers_explicit_source_manifest_path(){
  let(base,manifest,_)=fixture();let mut req=request("NEON_BATCH_TEST",manifest.with_file_name("missing-handoff.json").to_string_lossy().into_owned());
  req.source_manifest_path=Some(manifest.to_string_lossy().into_owned());req.selected_project_ids=vec!["001".into()];
  let resolved=resolve_vyron_manifest_for_request(&req).unwrap();
  assert_eq!(PathBuf::from(resolved).canonicalize().unwrap(),manifest.canonicalize().unwrap());
  fs::remove_dir_all(base).unwrap();
}

#[test]
fn vyron_manifest_filters_to_selected_project_ids(){
  let(base,manifest,status)=fixture();let root=manifest.parent().unwrap();let p2=root.join("002");fs::create_dir_all(&p2).unwrap();fs::write(p2.join("image.jpg"),b"image").unwrap();fs::write(p2.join("track_002.mp3"),b"audio").unwrap();
  let mut v:serde_json::Value=serde_json::from_slice(&fs::read(&manifest).unwrap()).unwrap();v["projectCount"]=json!(2);v["projects"].as_array_mut().unwrap().push(json!({"projectId":"002","folderPath":p2.to_string_lossy(),"tracks":[{"path":p2.join("track_002.mp3").to_string_lossy()}]}));fs::write(&manifest,serde_json::to_vec_pretty(&v).unwrap()).unwrap();
  let mut s:serde_json::Value=serde_json::from_slice(&fs::read(&status).unwrap()).unwrap();s["projects"].as_array_mut().unwrap().push(json!({"projectId":"002","renderStatus":"Waiting","outputFile":null,"duration":null,"fileSize":null,"error":null}));fs::write(&status,serde_json::to_vec_pretty(&s).unwrap()).unwrap();
  let info=load_vyron_batch_manifest(manifest.to_string_lossy().into_owned(),Some(vec!["002".into()])).unwrap();
  assert_eq!(info.project_count,1);assert_eq!(info.project_paths.len(),1);assert!(info.project_paths[0].ends_with("002"));
  assert!(PathBuf::from(info.output_dir).ends_with(PathBuf::from("Render").join("NEON")));
  fs::remove_dir_all(base).unwrap();
}
