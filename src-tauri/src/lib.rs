mod model;
mod scan;
mod persistence;
mod render;
mod fast_render;
mod visual_spec;
mod preview;
mod live_preview;
mod assets;
mod license;
mod benchmark;
mod queue;
mod cache;
mod system;
#[cfg(any(target_os="windows",target_os="macos"))]
#[path="updater_windows.rs"]
mod updater_local;
#[cfg(not(any(target_os="windows",target_os="macos")))]
mod updater_local;
mod mp4_manifest;
mod vyron_bridge;
#[cfg(test)]
mod mp4_manifest_probe_tests;
#[cfg(test)]
mod vyron_bridge_tests;

use std::sync::Arc;
#[cfg(feature="e2e-render")]
use std::sync::atomic::{AtomicBool,Ordering};
#[cfg(feature="e2e-render")]
static E2E_RENDER_ACTIVE:AtomicBool=AtomicBool::new(false);
use tauri::Manager;


// ENDLUME_COMMON_MP4_DISTRIBUTION_PAD: renderer-agnostic final deliverable size.
const FINAL_DISTRIBUTION_TARGET_MIB:u64=450;
fn finalize_distribution_output(mut summary:render::RenderOutcome)->Result<render::RenderOutcome,String>{
  use std::io::{Seek,SeekFrom,Write};
  let path=std::path::PathBuf::from(&summary.output_path);
  let is_mp4=path.extension().and_then(|x|x.to_str()).map(|x|x.eq_ignore_ascii_case("mp4")).unwrap_or(false);
  if !is_mp4{
    summary.output_bytes=std::fs::metadata(&path).ok().map(|m|m.len());
    return Ok(summary)
  }
  const MIB:u64=1024*1024;
  let current=std::fs::metadata(&path).map_err(|e|format!("distribution output metadata: {e}"))?.len();
  let target=FINAL_DISTRIBUTION_TARGET_MIB*MIB;
  if current>=target{
    summary.output_bytes=Some(current);
    return Ok(summary)
  }
  let pad=target-current;
  if pad<8{
    summary.output_bytes=Some(current);
    return Ok(summary)
  }
  let mut file=std::fs::OpenOptions::new().read(true).write(true).open(&path).map_err(|e|format!("distribution output open: {e}"))?;
  file.seek(SeekFrom::End(0)).map_err(|e|format!("distribution output seek: {e}"))?;
  if pad<=u32::MAX as u64{
    file.write_all(&(pad as u32).to_be_bytes()).map_err(|e|format!("distribution free header: {e}"))?;
    file.write_all(b"free").map_err(|e|format!("distribution free type: {e}"))?;
  }else{
    if pad<16{return Err("distribution free box is too small for extended size".into())}
    file.write_all(&1u32.to_be_bytes()).map_err(|e|format!("distribution extended header: {e}"))?;
    file.write_all(b"free").map_err(|e|format!("distribution extended type: {e}"))?;
    file.write_all(&pad.to_be_bytes()).map_err(|e|format!("distribution extended size: {e}"))?;
  }
  file.set_len(target).map_err(|e|format!("distribution output resize: {e}"))?;
  file.flush().map_err(|e|format!("distribution output flush: {e}"))?;
  let final_len=std::fs::metadata(&path).map_err(|e|format!("distribution output final metadata: {e}"))?.len();
  if final_len!=target{return Err(format!("distribution output size mismatch: expected={target} actual={final_len}"))}
  summary.output_bytes=Some(final_len);
  Ok(summary)
}

pub(crate) async fn render_with_phase3_fast(app:&tauri::AppHandle,job:&model::QueueJob,cancel:Arc<std::sync::atomic::AtomicBool>)->Result<render::RenderOutcome,String>{
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
}

#[cfg(feature="e2e-render")]
fn e2e_qa_mode()->bool{
  std::env::var_os("ENDLUME_E2E_PREVIEW_JOB").is_some()||std::env::var_os("ENDLUME_E2E_RENDER_JOB").is_some()
}

#[cfg(feature="e2e-render")]
async fn run_preview_e2e_case(app:tauri::AppHandle,value:serde_json::Value)->Result<serde_json::Value,String>{
  let project_path=value.get("projectPath").and_then(|x|x.as_str()).ok_or("preview projectPath missing")?.to_string();
  let overlay_source=value.get("overlaySource").and_then(|x|x.as_str()).ok_or("preview overlaySource missing")?.to_string();
  let time_sec=value.get("timeSec").and_then(|x|x.as_f64()).unwrap_or(0.0);
  let effects=serde_json::from_value::<Vec<model::EffectPreset>>(value.get("effects").cloned().unwrap_or_else(||serde_json::json!([]))).map_err(|e|format!("preview effects: {e}"))?;
  let subscribes=serde_json::from_value::<Vec<model::SubscribePreset>>(value.get("subscribes").cloned().unwrap_or_else(||serde_json::json!([]))).map_err(|e|format!("preview subscribes: {e}"))?;
  let helper=live_preview::prepare_live_preview(app.clone(),project_path.clone(),overlay_source,time_sec,Some("e1011-cold-preview".into()),Some(if subscribes.is_empty(){"Effects".into()}else{"Subscribe".into()})).await?;
  let poster=preview::generate_preview_poster(app.clone(),project_path.clone(),time_sec,effects.clone(),subscribes.clone(),Some("e1011-cold-preview-poster".into())).await?;
  let exact=preview::generate_preview(app,project_path,time_sec,effects,subscribes,Some("e1011-cold-preview".into())).await?;
  Ok(serde_json::json!({"helper":serde_json::to_value(helper).map_err(|e|e.to_string())?,"posterPath":poster,"exactPath":exact}))
}

#[cfg(feature="e2e-render")]
fn maybe_start_preview_e2e(app:tauri::AppHandle){
  E2E_RENDER_ACTIVE.store(true,Ordering::SeqCst);
  let Ok(fixture_path)=std::env::var("ENDLUME_E2E_PREVIEW_JOB") else{return};
  let Ok(result_path)=std::env::var("ENDLUME_E2E_RESULT") else{return};
  tauri::async_runtime::spawn(async move{
    let parsed=std::fs::read(&fixture_path)
      .map_err(|e|format!("preview fixture read: {e}"))
      .and_then(|bytes|serde_json::from_slice::<serde_json::Value>(&bytes).map_err(|e|format!("preview fixture json: {e}")));
    let result:Result<serde_json::Value,String>=async{
      let value=parsed?;
      if let Some(jobs)=value.get("jobs").and_then(|x|x.as_array()){
        let mut results=Vec::with_capacity(jobs.len());
        for item in jobs{
          let id=item.get("id").and_then(|x|x.as_str()).unwrap_or("preview-case").to_string();
          let payload=run_preview_e2e_case(app.clone(),item.clone()).await?;
          results.push(serde_json::json!({"id":id,"result":payload}));
        }
        Ok(serde_json::json!({"status":"passed","results":results}))
      }else{
        let payload=run_preview_e2e_case(app.clone(),value).await?;
        Ok(serde_json::json!({"status":"passed","result":payload}))
      }
    }.await;
    let (ok,payload)=match result{Ok(v)=>(true,v),Err(e)=>(false,serde_json::json!({"status":"failed","error":e}))};
    let _=std::fs::write(&result_path,serde_json::to_vec_pretty(&payload).unwrap_or_default());
    E2E_RENDER_ACTIVE.store(false,Ordering::SeqCst);
    app.exit(if ok{0}else{32});
  });
}

#[cfg(feature="e2e-render")]
fn maybe_start_render_e2e(app:tauri::AppHandle){
  E2E_RENDER_ACTIVE.store(true,Ordering::SeqCst);
  let Ok(fixture_path)=std::env::var("ENDLUME_E2E_RENDER_JOB") else{return};
  let Ok(result_path)=std::env::var("ENDLUME_E2E_RESULT") else{return};
  tauri::async_runtime::spawn(async move{
    let started_all=std::time::Instant::now();
    let parsed=std::fs::read(&fixture_path)
      .map_err(|e|format!("fixture read: {e}"))
      .and_then(|bytes|serde_json::from_slice::<serde_json::Value>(&bytes).map_err(|e|format!("fixture json: {e}")))
      .and_then(|value|{
        if value.is_array(){
          serde_json::from_value::<Vec<model::QueueJob>>(value).map_err(|e|format!("fixture jobs: {e}"))
        }else if let Some(jobs)=value.get("jobs"){
          serde_json::from_value::<Vec<model::QueueJob>>(jobs.clone()).map_err(|e|format!("fixture jobs: {e}"))
        }else{
          serde_json::from_value::<model::QueueJob>(value).map(|job|vec![job]).map_err(|e|format!("fixture job: {e}"))
        }
      });

    let mut results=Vec::<serde_json::Value>::new();
    let mut ok=true;
    if let Err(error)=license::assert_production_allowed(&app).await{
      ok=false;
      results.push(serde_json::json!({"status":"failed","stage":"license-gate","error":error}));
    }
    match parsed{
      Ok(jobs)=>{
        for job in jobs{
          if !ok{break}
          let id=job.project.id.clone();
          let started=std::time::Instant::now();
          match render_with_phase3_fast(&app,&job,Arc::new(std::sync::atomic::AtomicBool::new(false))).await{
            Ok(summary)=>{
              let terminal=queue::done_payload_from_summary(&job,&id,&summary);
              results.push(serde_json::json!({
                "id":id,
                "status":"passed",
                "wallSeconds":started.elapsed().as_secs_f64(),
                "terminal":terminal,
                "outputPath":summary.output_path,
                "outputBytes":summary.output_bytes,
                "encoder":summary.encoder,
                "finalDuration":summary.final_video_duration_seconds,
                "fastPath":summary.fast_path,
                "fastPathReason":summary.fast_path_reason,
                "audioMode":summary.audio_mode,
                "videoCodec":summary.video_codec,
                "audioCodec":summary.audio_codec
              }));
            }
            Err(error)=>{
              ok=false;
              results.push(serde_json::json!({"id":id,"status":"failed","wallSeconds":started.elapsed().as_secs_f64(),"error":error}));
              break;
            }
          }
        }
      }
      Err(error)=>{
        ok=false;
        results.push(serde_json::json!({"status":"failed","error":error}));
      }
    }
    let payload=serde_json::json!({
      "status":if ok{"passed"}else{"failed"},
      "wallSeconds":started_all.elapsed().as_secs_f64(),
      "results":results
    });
    let _=std::fs::write(&result_path,serde_json::to_vec_pretty(&payload).unwrap_or_default());
    E2E_RENDER_ACTIVE.store(false,Ordering::SeqCst);
    app.exit(if ok{0}else{31});
  });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run(){
  #[cfg(feature="e2e-render")]
  let e2e_qa=e2e_qa_mode();
  #[cfg(not(feature="e2e-render"))]
  let e2e_qa=false;

  let mut context=tauri::generate_context!();
  #[cfg(all(feature="e2e-render",target_os="macos"))]
  if e2e_qa{
    for window in &mut context.config_mut().app.windows{
      if window.label=="main"{
        window.visible=false;
        window.focus=false;
        window.focusable=false;
      }
    }
  }

  let app=tauri::Builder::default()
    .manage(Arc::new(queue::QueueRuntime::default()))
    .plugin(tauri_plugin_dialog::init())
    .plugin(tauri_plugin_fs::init())
    .plugin(tauri_plugin_opener::init())
    .plugin(tauri_plugin_process::init())
    .plugin(tauri_plugin_updater::Builder::new().build())
    .plugin(tauri_plugin_shell::init())
    .invoke_handler(tauri::generate_handler![
      scan::scan_root,
      queue::enqueue_projects,queue::queue_snapshot,queue::reorder_queue,queue::cancel_project,queue::resume_recovery,queue::resume_license_queue,
      preview::generate_preview,preview::generate_preview_poster,preview::preview_frontend_fixture,preview::preview_frontend_report,live_preview::prepare_live_preview,assets::import_library_asset,
      persistence::load_library,persistence::save_library,persistence::load_recovery,persistence::dismiss_recovery,
      benchmark::benchmark_engine,
      license::activate_license,license::license_status,license::set_license_screen,license::set_license_queue_depth,
      cache::cache_stats,cache::clear_effect_cache,
      system::power_status,system::disk_status,system::cleanup_duplicate_apps,system::normalize_current_app_name,system::open_result_path,system::reveal_result_path,
      updater_local::local_update_check,updater_local::local_update_start,updater_local::local_update_status,
      vyron_bridge::consume_vyron_batch_request,vyron_bridge::load_vyron_batch_manifest,vyron_bridge::report_vyron_render
    ])
    .on_page_load(|webview,_payload|{
      if webview.label()=="main"{
        if let Ok(marker)=std::env::var("ENDLUME_LAUNCH_SMOKE_MARKER"){
          let payload=serde_json::json!({
            "label":"main",
            "frontendLoaded":true,
            "pid":std::process::id()
          });
          let _=std::fs::write(marker,serde_json::to_vec_pretty(&payload).unwrap_or_default());
        }
      }
    })
    .setup(move |app|{
      #[cfg(all(feature="e2e-render",target_os="macos"))]
      if e2e_qa{
        app.handle().set_activation_policy(tauri::ActivationPolicy::Accessory)?;
        app.handle().set_dock_visibility(false)?;
        if let Some(main)=app.get_webview_window("main"){let _=main.hide();}
      }
      persistence::mark_session_open(&app.handle().clone())?;
      render::cleanup_runtime_caches_1003(&app.handle().clone());
      #[cfg(feature="e2e-render")]
      if std::env::var_os("ENDLUME_E2E_PREVIEW_JOB").is_some(){
        maybe_start_preview_e2e(app.handle().clone());
        return Ok(())
      }
      #[cfg(feature="e2e-render")]
      if std::env::var_os("ENDLUME_E2E_RENDER_JOB").is_some(){
        maybe_start_render_e2e(app.handle().clone());
        return Ok(())
      }
      cache::start_strict_prewarm_856(app.handle().clone());
      license::start_heartbeat(app.handle().clone());
      Ok(())
    })
    .on_window_event(|window,event|{
      #[cfg(feature="e2e-render")]
      if std::env::var_os("ENDLUME_E2E_RENDER_JOB").is_some(){
        if let tauri::WindowEvent::CloseRequested{api,..}=event{api.prevent_close();return}
      }
      if let tauri::WindowEvent::Destroyed=event{let _=persistence::mark_session_closed(window.app_handle());}
    })
    .build(context)
    .expect("error while building ENDLUME");
  app.run(|_app_handle,event|{
    #[cfg(feature="e2e-render")]
    if E2E_RENDER_ACTIVE.load(Ordering::SeqCst){
      if let tauri::RunEvent::ExitRequested{api,..}=event{api.prevent_exit();}
    }
  });
}