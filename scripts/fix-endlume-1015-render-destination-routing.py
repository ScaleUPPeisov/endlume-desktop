#!/usr/bin/env python3
from pathlib import Path

QUEUE = Path('src-tauri/src/queue.rs')
LIB = Path('src-tauri/src/lib.rs')

q = QUEUE.read_text(encoding='utf-8')
lib = LIB.read_text(encoding='utf-8')

marker = 'ENDLUME_VYRON_RENDER_DESTINATION_ROUTING_HOTFIX'
if marker not in q:
    old_use = "use std::{collections::{HashSet,VecDeque},fs,path::PathBuf,sync::{Arc,atomic::{AtomicBool,Ordering}},time::{Instant,UNIX_EPOCH}};"
    new_use = "use std::{collections::{HashSet,VecDeque},fs,path::{Path,PathBuf},sync::{Arc,atomic::{AtomicBool,Ordering}},time::{Instant,UNIX_EPOCH}};"
    if old_use not in q:
        raise SystemExit('queue import anchor missing')
    q = q.replace(old_use, new_use, 1)

    anchor = "fn queue_safe_name(name:&str)->String{name.chars().map(|c|if ['/', '\\\\', ':', '*', '?', '\"', '<', '>', '|'].contains(&c){'_'}else{c}).collect()}\n"
    if anchor not in q:
        raise SystemExit('queue_safe_name anchor missing')
    helper = r'''

// ENDLUME_VYRON_RENDER_DESTINATION_ROUTING_HOTFIX
// VYRON project metadata owns the final destination. ProductionManager/Batches
// remains orchestration/workspace only and is never accepted as final output.
#[derive(Clone,Debug)]
pub(crate) struct VyronRenderRoute{
  vyron_root:String,
  channel:String,
  project_directory:String,
  batch_directory:String,
  final_render_directory:String,
}

fn is_vyron_managed(project:&ProjectScanItem)->bool{
  project.output_source.as_deref().map(str::trim).map(|s|s.eq_ignore_ascii_case("vyron")).unwrap_or(false)
    || project.vyron_manifest_path.as_deref().map(str::trim).map(|s|!s.is_empty()).unwrap_or(false)
    || project.vyron_channel_name.as_deref().map(str::trim).map(|s|!s.is_empty()).unwrap_or(false)
}

fn canonical_existing(path:&Path,label:&str)->Result<PathBuf,String>{
  path.canonicalize().map_err(|e|format!("VYRON routing: {label} недоступен: {} ({e})",path.display()))
}

fn resolve_vyron_render_route(project:&ProjectScanItem)->Result<Option<VyronRenderRoute>,String>{
  if !is_vyron_managed(project){return Ok(None)}
  let channel=project.vyron_channel_name.as_deref().map(str::trim).filter(|s|!s.is_empty()).ok_or_else(||format!("VYRON routing: project '{}' не содержит persisted channel identity",project.name))?;
  if channel=="."||channel==".."||channel.chars().any(|c|c=='/'||c=='\\'){
    return Err(format!("VYRON routing: некорректное channel name '{}' для project '{}'",channel,project.name))
  }

  let project_dir=canonical_existing(Path::new(&project.path),"PROJECT DIRECTORY")?;
  let production_manager=project_dir.ancestors().find(|p|p.file_name().and_then(|x|x.to_str()).map(|x|x.eq_ignore_ascii_case("ProductionManager")).unwrap_or(false))
    .ok_or_else(||format!("VYRON routing: PROJECT DIRECTORY '{}' не находится внутри ProductionManager",project_dir.display()))?;
  let vyron_root=production_manager.parent().ok_or_else(||format!("VYRON routing: не удалось определить VYRON ROOT для '{}'",project.name))?.to_path_buf();
  let vyron_root=canonical_existing(&vyron_root,"VYRON ROOT")?;
  let batches_root=canonical_existing(&vyron_root.join("ProductionManager").join("Batches"),"ProductionManager/Batches")?;

  let batch_dir=project.vyron_manifest_path.as_deref().map(str::trim).filter(|s|!s.is_empty())
    .and_then(|s|Path::new(s).parent().map(Path::to_path_buf))
    .or_else(||project_dir.parent().map(Path::to_path_buf))
    .ok_or_else(||format!("VYRON routing: не удалось определить BATCH DIRECTORY для '{}'",project.name))?;
  let batch_dir=canonical_existing(&batch_dir,"BATCH DIRECTORY")?;

  let expected=vyron_root.join("Render").join(channel);
  fs::create_dir_all(&expected).map_err(|e|format!("VYRON routing: не удалось создать FINAL RENDER DIRECTORY '{}': {e}",expected.display()))?;
  let expected=canonical_existing(&expected,"FINAL RENDER DIRECTORY")?;

  let resolved=if let Some(raw)=project.output_dir.as_deref().map(str::trim).filter(|s|!s.is_empty()){
    let supplied=PathBuf::from(raw);
    fs::create_dir_all(&supplied).map_err(|e|format!("VYRON routing: persisted outputDirectory '{}' недоступен: {e}",supplied.display()))?;
    canonical_existing(&supplied,"persisted outputDirectory")?
  }else{
    // Deterministic recovery is allowed only when persisted output metadata is
    // absent: VYRON ROOT + Render + persisted channel identity.
    expected.clone()
  };

  if resolved.starts_with(&batches_root){
    return Err(format!("VYRON routing blocked BATCH_OUTPUT_LEAK: project='{}' final='{}' batches='{}'",project.name,resolved.display(),batches_root.display()))
  }
  if resolved!=expected{
    return Err(format!("VYRON routing destination mismatch for project '{}': persisted='{}' expected='{}'",project.name,resolved.display(),expected.display()))
  }

  Ok(Some(VyronRenderRoute{
    vyron_root:vyron_root.to_string_lossy().into_owned(),
    channel:channel.to_string(),
    project_directory:project_dir.to_string_lossy().into_owned(),
    batch_directory:batch_dir.to_string_lossy().into_owned(),
    final_render_directory:expected.to_string_lossy().into_owned(),
  }))
}

pub(crate) fn enforce_render_destination(job:&mut QueueJob)->Result<bool,String>{
  let Some(route)=resolve_vyron_render_route(&job.project)? else{return Ok(false)};
  job.settings.output_dir=route.final_render_directory.clone();
  job.project.output_dir=Some(route.final_render_directory);
  job.project.output_source=Some("vyron".into());
  Ok(true)
}

pub(crate) fn log_render_route(job:&QueueJob){
  let Ok(Some(route))=resolve_vyron_render_route(&job.project) else{return};
  eprintln!("VYRON ROOT={}",route.vyron_root);
  eprintln!("CHANNEL={}",route.channel);
  eprintln!("PROJECT DIRECTORY={}",route.project_directory);
  eprintln!("BATCH DIRECTORY={}",route.batch_directory);
  eprintln!("FINAL RENDER DIRECTORY={}",route.final_render_directory);
}

pub(crate) fn log_final_output(job:&QueueJob,output_file:&str){
  if is_vyron_managed(&job.project){eprintln!("FINAL OUTPUT FILE={output_file}")}
}
'''
    q = q.replace(anchor, anchor + helper, 1)

    old_empty = '  if settings.output_dir.trim().is_empty(){return Err("Не выбрана папка результата".into())}'
    new_empty = '  if settings.output_dir.trim().is_empty()&&projects.iter().filter(|p|p.valid).any(|p|!is_vyron_managed(p)){return Err("Не выбрана папка результата".into())}'
    if old_empty not in q:
        raise SystemExit('settings output-dir guard anchor missing')
    q = q.replace(old_empty, new_empty, 1)

    old_prepared = '  let mut prepared=Vec::<(ProjectScanItem,Vec<EffectPreset>)>::new();'
    new_prepared = '  let mut prepared=Vec::<QueueJob>::new();'
    if old_prepared not in q:
        raise SystemExit('prepared vector anchor missing')
    q = q.replace(old_prepared, new_prepared, 1)

    old_push = '    prepared.push((project,selected));'
    new_push = '''    let mut job=QueueJob{project,settings:settings.clone(),effects:selected,subscribes:subscribes.clone(),ambient:ambient.clone(),ambient_settings:ambient_settings.clone()};
    enforce_render_destination(&mut job)?;
    prepared.push(job);'''
    if old_push not in q:
        raise SystemExit('prepared push anchor missing')
    q = q.replace(old_push, new_push, 1)

    old_queue = '''    for (project,selected_effects) in prepared{
      if !occupied.insert(project.id.clone()){continue}
      runtime.clear_terminal(&project.id);
      q.push_back(QueueJob{project,settings:settings.clone(),effects:selected_effects,subscribes:subscribes.clone(),ambient:ambient.clone(),ambient_settings:ambient_settings.clone()});
    }'''
    new_queue = '''    for job in prepared{
      if !occupied.insert(job.project.id.clone()){continue}
      runtime.clear_terminal(&job.project.id);
      q.push_back(job);
    }'''
    if old_queue not in q:
        raise SystemExit('queue insertion anchor missing')
    q = q.replace(old_queue, new_queue, 1)

    q = q.replace('match validate_recovered_effect_contract(&mut job){', 'match validate_recovered_job(&mut job){')
    useful_anchor = '\nfn useful_detail(raw:&str)->String{'
    if useful_anchor not in q:
        raise SystemExit('useful_detail anchor missing')
    recovered_helper = '''
fn validate_recovered_job(job:&mut QueueJob)->Result<(),String>{
  validate_recovered_effect_contract(job)?;
  enforce_render_destination(job).map(|_|())
}
'''
    q = q.replace(useful_anchor, recovered_helper + useful_anchor, 1)

    tests = r'''

#[cfg(test)]
mod render_destination_routing_tests{
  use super::*;
  use uuid::Uuid;

  fn fixture(channel:&str,explicit_output:bool)->(PathBuf,QueueJob,PathBuf,PathBuf){
    let base=std::env::temp_dir().join(format!("endlume-routing-{}",Uuid::new_v4()));
    let vyron=base.join("VYRON");
    let batch=vyron.join("ProductionManager").join("Batches").join("batch-001");
    let project_dir=batch.join("project-001");
    let expected=vyron.join("Render").join(channel);
    fs::create_dir_all(&project_dir).unwrap();
    fs::create_dir_all(&expected).unwrap();
    let project=ProjectScanItem{
      id:"routing-test".into(),name:"routing-test".into(),path:project_dir.to_string_lossy().into_owned(),media:vec![],audio:vec![],valid:true,error:None,anchors:None,
      selected_effect_id:None,selected_effect_ids:vec![],
      output_dir:if explicit_output{Some(expected.to_string_lossy().into_owned())}else{None},
      output_source:Some("vyron".into()),
      vyron_manifest_path:Some(batch.join("batch.json").to_string_lossy().into_owned()),
      vyron_channel_name:Some(channel.into()),
    };
    let settings=RenderSettings{width:1920,height:1080,fps:60,codec:"h265".into(),bitrate_mbps:30.0,duration_hours:1.0,duration_mode:"auto".into(),loop_mode:"image".into(),crossfade_sec:0.0,normalize_lufs:false,output_dir:project_dir.to_string_lossy().into_owned(),preset:"fast".into(),encoder_preference:"auto".into()};
    let job=QueueJob{project,settings,effects:vec![],subscribes:vec![],ambient:None,ambient_settings:BackgroundMusicSettings::default()};
    (base,job,expected,project_dir)
  }

  #[test]
  fn vyron_explicit_project_output_overrides_poisoned_batch_settings(){
    let(base,mut job,expected,project_dir)=fixture("Afterglow Highway",true);
    assert_eq!(PathBuf::from(&job.settings.output_dir),project_dir);
    assert!(enforce_render_destination(&mut job).unwrap());
    assert_eq!(PathBuf::from(&job.settings.output_dir).canonicalize().unwrap(),expected.canonicalize().unwrap());
    assert_eq!(PathBuf::from(job.project.output_dir.as_deref().unwrap()).canonicalize().unwrap(),expected.canonicalize().unwrap());
    fs::remove_dir_all(base).unwrap();
  }

  #[test]
  fn vyron_missing_output_metadata_recovers_root_render_channel(){
    let(base,mut job,expected,_)=fixture("Aether Riff",false);
    assert!(enforce_render_destination(&mut job).unwrap());
    assert_eq!(PathBuf::from(&job.settings.output_dir).canonicalize().unwrap(),expected.canonicalize().unwrap());
    assert_eq!(PathBuf::from(job.project.output_dir.as_deref().unwrap()).canonicalize().unwrap(),expected.canonicalize().unwrap());
    fs::remove_dir_all(base).unwrap();
  }

  #[test]
  fn vyron_recovery_repairs_legacy_serialized_batch_destination(){
    let(base,job,expected,project_dir)=fixture("Aegean Afterglow",true);
    let bytes=serde_json::to_vec(&job).unwrap();
    let mut restored:QueueJob=serde_json::from_slice(&bytes).unwrap();
    restored.settings.output_dir=project_dir.to_string_lossy().into_owned();
    assert!(enforce_render_destination(&mut restored).unwrap());
    assert_eq!(PathBuf::from(&restored.settings.output_dir).canonicalize().unwrap(),expected.canonicalize().unwrap());
    fs::remove_dir_all(base).unwrap();
  }

  #[test]
  fn vyron_batch_directory_is_rejected_as_final_output(){
    let(base,mut job,_expected,project_dir)=fixture("After Dark Voice",true);
    job.project.output_dir=Some(project_dir.to_string_lossy().into_owned());
    let err=enforce_render_destination(&mut job).unwrap_err();
    assert!(err.contains("BATCH_OUTPUT_LEAK"),"{err}");
    fs::remove_dir_all(base).unwrap();
  }

  #[test]
  fn standalone_endlume_keeps_existing_output_behavior(){
    let base=std::env::temp_dir().join(format!("endlume-standalone-routing-{}",Uuid::new_v4()));
    let project_dir=base.join("project");let output=base.join("standalone-output");fs::create_dir_all(&project_dir).unwrap();fs::create_dir_all(&output).unwrap();
    let project=ProjectScanItem{id:"standalone".into(),name:"standalone".into(),path:project_dir.to_string_lossy().into_owned(),media:vec![],audio:vec![],valid:true,error:None,anchors:None,selected_effect_id:None,selected_effect_ids:vec![],output_dir:None,output_source:None,vyron_manifest_path:None,vyron_channel_name:None};
    let settings=RenderSettings{width:1920,height:1080,fps:60,codec:"h265".into(),bitrate_mbps:30.0,duration_hours:1.0,duration_mode:"auto".into(),loop_mode:"image".into(),crossfade_sec:0.0,normalize_lufs:false,output_dir:output.to_string_lossy().into_owned(),preset:"fast".into(),encoder_preference:"auto".into()};
    let mut job=QueueJob{project,settings,effects:vec![],subscribes:vec![],ambient:None,ambient_settings:BackgroundMusicSettings::default()};
    assert!(!enforce_render_destination(&mut job).unwrap());
    assert_eq!(PathBuf::from(&job.settings.output_dir).canonicalize().unwrap(),output.canonicalize().unwrap());
    fs::remove_dir_all(base).unwrap();
  }
}
'''
    q += tests

lib_marker = 'ENDLUME_VYRON_FINAL_WRITER_ROUTE_GUARD'
if lib_marker not in lib:
    old = '''pub(crate) async fn render_with_phase3_fast(app:&tauri::AppHandle,job:&model::QueueJob,cancel:Arc<std::sync::atomic::AtomicBool>)->Result<render::RenderOutcome,String>{
  let summary=match fast_render::try_render_job(app,job,cancel.clone()).await?{
    Some(summary)=>summary,
    None=>render::render_job(app,job,cancel).await?,
  };
  finalize_distribution_output(summary)
}'''
    new = '''pub(crate) async fn render_with_phase3_fast(app:&tauri::AppHandle,job:&model::QueueJob,cancel:Arc<std::sync::atomic::AtomicBool>)->Result<render::RenderOutcome,String>{
  // ENDLUME_VYRON_FINAL_WRITER_ROUTE_GUARD
  // Re-assert routing at the renderer boundary so queue/import/recovery regressions
  // can never silently leak a VYRON final file into ProductionManager/Batches.
  let mut routed_job=job.clone();
  let vyron_managed=queue::enforce_render_destination(&mut routed_job)?;
  if vyron_managed{queue::log_render_route(&routed_job);}
  let summary=match fast_render::try_render_job(app,&routed_job,cancel.clone()).await?{
    Some(summary)=>summary,
    None=>render::render_job(app,&routed_job,cancel).await?,
  };
  let summary=finalize_distribution_output(summary)?;
  if vyron_managed{queue::log_final_output(&routed_job,&summary.output_path);}
  Ok(summary)
}'''
    if old not in lib:
        raise SystemExit('render_with_phase3_fast anchor missing')
    lib = lib.replace(old, new, 1)

QUEUE.write_text(q,encoding='utf-8')
LIB.write_text(lib,encoding='utf-8')
print('ENDLUME_VYRON_RENDER_DESTINATION_ROUTING_PATCH=APPLIED')
