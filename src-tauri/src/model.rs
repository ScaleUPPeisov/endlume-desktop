use serde::{Deserialize,Serialize};
use std::collections::HashMap;

#[derive(Debug,Clone,Serialize,Deserialize)]
#[serde(rename_all="camelCase")]
pub struct AnchorPoint{
  pub x:f64,
  pub y:f64,
  #[serde(default)] pub width:Option<f64>,
  #[serde(default)] pub height:Option<f64>,
  #[serde(default)] pub source:Option<String>,
  #[serde(default)] pub confidence:Option<f64>,
}

#[derive(Debug,Clone,Serialize,Deserialize)]
#[serde(rename_all="camelCase")]
pub struct ProjectScanItem{
  pub id:String,
  pub name:String,
  pub path:String,
  pub media:Vec<String>,
  pub audio:Vec<String>,
  pub valid:bool,
  pub error:Option<String>,
  #[serde(default)] pub anchors:Option<HashMap<String,AnchorPoint>>,
  #[serde(default)] pub selected_effect_id:Option<String>
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
  #[serde(default)] pub asset_state:Option<String>,
  #[serde(default)] pub asset_error:Option<String>,
  #[serde(default)] pub usage_mode:Option<String>,
  #[serde(default)] pub interval_sec:Option<f64>,
  #[serde(default)] pub usage_duration_sec:Option<f64>,
  #[serde(default)] pub target:Option<String>,
  #[serde(default)] pub offset_x:Option<f64>,
  #[serde(default)] pub offset_y:Option<f64>,
  #[serde(default)] pub opacity:Option<f64>,
}

#[derive(Debug,Clone,Serialize,Deserialize)]
#[serde(rename_all="camelCase")]
pub struct SubscribePreset{
  #[serde(flatten)] pub effect:EffectPreset,
  pub first_at_sec:f64,
  pub second_at_sec:f64,
  pub repeat_every_sec:f64,
  #[serde(default)] pub first_appearance:Option<String>,
  #[serde(default)] pub custom_first_at_sec:Option<f64>,
  #[serde(default)] pub show_duration_sec:Option<f64>
}

#[derive(Debug,Clone,Serialize,Deserialize)]
#[serde(rename_all="camelCase")]
pub struct BackgroundMusicSettings{
  #[serde(default="default_background_volume")] pub volume_pct:f64,
  #[serde(default)] pub bass_db:f64,
  #[serde(default)] pub mid_db:f64,
  #[serde(default)] pub treble_db:f64,
}
fn default_background_volume()->f64{18.0}
impl Default for BackgroundMusicSettings{
  fn default()->Self{Self{volume_pct:18.0,bass_db:0.0,mid_db:0.0,treble_db:0.0}}
}

#[derive(Debug,Clone,Serialize,Deserialize)]
#[serde(rename_all="camelCase")]
pub struct QueueJob{
  pub project:ProjectScanItem,
  pub settings:RenderSettings,
  pub effects:Vec<EffectPreset>,
  pub subscribes:Vec<SubscribePreset>,
  pub ambient:Option<String>,
  #[serde(default)] pub ambient_settings:BackgroundMusicSettings,
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
