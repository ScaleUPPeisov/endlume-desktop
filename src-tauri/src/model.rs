use serde::{Deserialize,Serialize};

#[derive(Debug,Clone,Serialize,Deserialize)]
#[serde(rename_all="camelCase")]
pub struct ProjectScanItem{
  pub id:String,
  pub name:String,
  pub path:String,
  pub media:Vec<String>,
  pub audio:Vec<String>,
  pub valid:bool,
  pub error:Option<String>
}

#[derive(Debug,Clone,Serialize,Deserialize)]
#[serde(rename_all="camelCase")]
pub struct RenderSettings{
  pub width:u32,
  pub height:u32,
  pub fps:u32,
  pub codec:String,
  pub bitrate_mbps:f64,
  pub duration_hours:f64,
  pub duration_mode:String,
  pub loop_mode:String,
  pub crossfade_sec:f64,
  pub normalize_lufs:bool,
  pub output_dir:String,
  pub preset:String,
  pub encoder_preference:String,
}

#[derive(Debug,Clone,Serialize,Deserialize)]
#[serde(rename_all="camelCase")]
pub struct EffectPreset{
  pub id:String,
  pub name:String,
  pub source:String,
  pub enabled:bool,
  pub mode:String,
  pub key_color:String,
  pub similarity:f64,
  pub blend:f64,
  pub despill:f64,
  pub luma_threshold:f64,
  pub luma_tolerance:f64,
  pub saturation:f64,
  pub x:f64,
  pub y:f64,
  pub scale:f64,
  pub fullscreen:bool,
  pub preview_frame_time:f64,
  pub start_sec:f64,
  pub end_sec:Option<f64>,
  pub cache_key:Option<String>,
  pub cache_ready:Option<bool>,
}

#[derive(Debug,Clone,Serialize,Deserialize)]
#[serde(rename_all="camelCase")]
pub struct SubscribePreset{
  #[serde(flatten)] pub effect:EffectPreset,
  pub first_at_sec:f64,
  pub second_at_sec:f64,
  pub repeat_every_sec:f64
}

#[derive(Debug,Clone,Serialize,Deserialize)]
#[serde(rename_all="camelCase")]
pub struct QueueJob{
  pub project:ProjectScanItem,
  pub settings:RenderSettings,
  pub effects:Vec<EffectPreset>,
  pub subscribes:Vec<SubscribePreset>,
  pub ambient:Option<String>,
}

#[derive(Debug,Clone,Serialize,Deserialize)]
#[serde(rename_all="camelCase")]
pub struct Progress{
  pub id:String,
  pub status:String,
  pub progress:f64,
  pub stage:String,
  #[serde(skip_serializing_if="Option::is_none")] pub started_at:Option<i64>,
  pub elapsed_sec:f64,
  #[serde(skip_serializing_if="Option::is_none")] pub eta_sec:Option<f64>,
  #[serde(skip_serializing_if="Option::is_none")] pub result_path:Option<String>,
  #[serde(skip_serializing_if="Option::is_none")] pub result_bytes:Option<u64>,
  #[serde(skip_serializing_if="Option::is_none")] pub actual_video_bitrate:Option<u64>,
  #[serde(skip_serializing_if="Option::is_none")] pub cpu_pct:Option<f32>,
  #[serde(skip_serializing_if="Option::is_none")] pub ram_bytes:Option<u64>,
  #[serde(skip_serializing_if="Option::is_none")] pub ram_total_bytes:Option<u64>,
  #[serde(skip_serializing_if="Option::is_none")] pub ram_available_bytes:Option<u64>,
  #[serde(skip_serializing_if="Option::is_none")] pub gpu_pct:Option<f32>,
  #[serde(skip_serializing_if="Option::is_none")] pub encoder:Option<String>,
  #[serde(skip_serializing_if="Option::is_none")] pub attempt:Option<u32>,
}
