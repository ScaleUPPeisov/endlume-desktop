mod model;
mod scan;
mod persistence;
mod render;
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
use tauri::Manager;

fn maybe_start_render_e2e(app:tauri::AppHandle){
  let Ok(fixture_path)=std::env::var("ENDLUME_E2E_RENDER_JOB") else{return};
  let Ok(result_path)=std::env::var("ENDLUME_E2E_RESULT") else{return};
  tauri::async_runtime::spawn(async move{
    let started=std::time::Instant::now();
    let payload=match std::fs::read(&fixture_path)
      .map_err(|e|format!("fixture read: {e}"))
      .and_then(|bytes|serde_json::from_slice::<model::QueueJob>(&bytes).map_err(|e|format!("fixture json: {e}"))){
      Ok(job)=>{
        let id=job.project.id.clone();
        match render::render_job(&app,&job,Arc::new(std::sync::atomic::AtomicBool::new(false))).await{
          Ok(summary)=>{
            let terminal=queue::done_payload_from_summary(&job,&id,&summary);
            serde_json::json!({
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
            })
          }
          Err(error)=>serde_json::json!({"status":"failed","wallSeconds":started.elapsed().as_secs_f64(),"error":error})
        }
      }
      Err(error)=>serde_json::json!({"status":"failed","wallSeconds":started.elapsed().as_secs_f64(),"error":error})
    };
    let ok=payload.get("status").and_then(|v|v.as_str())==Some("passed");
    let _=std::fs::write(&result_path,serde_json::to_vec_pretty(&payload).unwrap_or_default());
    app.exit(if ok{0}else{31});
  });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run(){
  tauri::Builder::default()
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
      preview::generate_preview,live_preview::prepare_live_preview,assets::import_library_asset,
      persistence::load_library,persistence::save_library,persistence::load_recovery,persistence::dismiss_recovery,
      benchmark::benchmark_engine,
      license::activate_license,license::license_status,license::set_license_screen,license::set_license_queue_depth,
      cache::cache_stats,cache::clear_effect_cache,
      system::power_status,system::disk_status,system::cleanup_duplicate_apps,system::normalize_current_app_name,system::open_result_path,system::reveal_result_path,
      updater_local::local_update_check,updater_local::local_update_start,updater_local::local_update_status,
      vyron_bridge::consume_vyron_batch_request,vyron_bridge::load_vyron_batch_manifest,vyron_bridge::report_vyron_render
    ])
    .setup(|app|{
      persistence::mark_session_open(&app.handle().clone())?;
      if std::env::var_os("ENDLUME_E2E_RENDER_JOB").is_some(){
        maybe_start_render_e2e(app.handle().clone());
      }else{
        cache::start_strict_prewarm_856(app.handle().clone());
        license::start_heartbeat(app.handle().clone());
      }
      Ok(())
    })
    .on_window_event(|window,event|{
      if let tauri::WindowEvent::Destroyed=event{let _=persistence::mark_session_closed(window.app_handle());}
    })
    .run(tauri::generate_context!())
    .expect("error while running ENDLUME");
}
