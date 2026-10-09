mod model;
mod scan;
mod persistence;
mod render;
mod fast_render;
mod preview;
mod license;
mod benchmark;
mod queue;
mod cache;
mod system;
#[cfg(feature="acceptance-harness")]
mod acceptance;
pub mod mp4_manifest;

use std::sync::Arc;
use tauri::Manager;

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
      queue::enqueue_projects,queue::queue_snapshot,queue::reorder_queue,queue::cancel_project,queue::resume_recovery,
      preview::generate_preview,
      persistence::load_library,persistence::save_library,persistence::load_recovery,persistence::dismiss_recovery,
      benchmark::benchmark_engine,
      license::activate_license,license::license_status,
      cache::cache_stats,cache::clear_effect_cache,
      system::power_status,system::open_result_path,system::reveal_result_path
    ])
    .setup(|app|{
      persistence::mark_session_open(&app.handle().clone())?;
      #[cfg(feature="acceptance-harness")]
      if std::env::var_os("ENDLUME_ACCEPTANCE_JOB").is_some(){
        let handle=app.handle().clone();
        tauri::async_runtime::spawn(async move{acceptance::run(handle).await;});
      }
      Ok(())
    })
    .on_window_event(|window,event|{
      if let tauri::WindowEvent::Destroyed=event{let _=persistence::mark_session_closed(window.app_handle());}
    })
    .run(tauri::generate_context!())
    .expect("error while running ENDLUME");
}
