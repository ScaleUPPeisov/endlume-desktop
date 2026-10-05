mod model;
mod scan;
mod persistence;
mod render;
mod audio_1013;
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
      let project_path=value.get("projectPath").and_then(|x|x.as_str()).ok_or("preview projectPath missing")?.to_string();
      let overlay_source=value.get("overlaySource").and_then(|x|x.as_str()).ok_or("preview overlaySource missing")?.to_string();
      let time_sec=value.get("timeSec").and_then(|x|x.as_f64()).unwrap_or(0.0);
      let effects=serde_json::from_value::<Vec<model::EffectPreset>>(value.get("effects").cloned().unwrap_or_else(||serde_json::json!([]))).map_err(|e|format!("preview effects: {e}"))?;
      let subscribes=serde_json::from_value::<Vec<model::SubscribePreset>>(value.get("subscribes").cloned().unwrap_or_else(||serde_json::json!([]))).map_err(|e|format!("preview subscribes: {e}"))?;
      let helper=live_preview::prepare_live_preview(app.clone(),project_path.clone(),overlay_source,time_sec,Some("e1011-cold-preview".into()),Some(if subscribes.is_empty(){"Effects".into()}else{"Subscribe".into()})).await?;
      let poster=preview::generate_preview_poster(app.clone(),project_path.clone(),time_sec,effects.clone(),subscribes.clone(),Some("e1011-cold-preview-poster".into())).await?;
      let exact=preview::generate_preview(app.clone(),project_path,time_sec,effects,subscribes,Some("e1011-cold-preview".into())).await?;
      Ok(serde_json::json!({"helper":serde_json::to_value(helper).map_err(|e|e.to_string())?,"posterPath":poster,"exactPath":exact}))
    }.await;
    let (ok,payload)=match result{Ok(v)=>(true,serde_json::json!({"status":"passed","result":v})),Err(e)=>(false,serde_json::json!({"status":"failed","error":e}))};
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
          match render::render_job(&app,&job,Arc::new(std::sync::atomic::AtomicBool::new(false))).await{
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
    .setup(|app|{
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
    .build(tauri::generate_context!())
    .expect("error while building ENDLUME");
  app.run(|_app_handle,event|{
    #[cfg(feature="e2e-render")]
    if E2E_RENDER_ACTIVE.load(Ordering::SeqCst){
      if let tauri::RunEvent::ExitRequested{api,..}=event{api.prevent_exit();}
    }
  });
}