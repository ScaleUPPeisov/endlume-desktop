use crate::{cache,model::EffectPreset};

pub const MAX_FAST_COMMON_PERIOD_SEC:f64=30.0;

fn color_ffmpeg(hex:&str)->String{
  format!("0x{}",hex.trim().trim_start_matches('#').trim_start_matches("0x"))
}

pub fn base_filter(label:&str,width:u32,height:u32,fps:u32)->String{
  // Canonical render.rs semantics: cover the canvas and crop from center.
  format!("[{label}]scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,crop={width}:{height}:(iw-ow)/2:(ih-oh)/2,fps={},setsar=1",fps.max(1))
}

pub fn active_effects_at(effects:&[EffectPreset],t:f64,final_duration:f64)->Vec<EffectPreset>{
  effects.iter().filter(|e|{
    e.enabled
      && e.usage_mode.as_deref().unwrap_or("legacy")!="off"
      && !e.source.trim().is_empty()
      && e.start_sec<=t+0.000_001
      && e.end_sec.unwrap_or(final_duration)>t
  }).cloned().collect()
}

pub fn fast_periodic_effect_supported(e:&EffectPreset)->bool{
  let usage=e.usage_mode.as_deref().unwrap_or("legacy");
  e.enabled
    && matches!(usage,"always"|"legacy")
    && !e.source.trim().is_empty()
    && e.start_sec.abs()<=0.000_1
    && e.end_sec.is_none()
    && matches!(e.mode.as_str(),"screen"|"chromakey"|"luma")
}

pub fn effect_phase_at(t:f64,e:&EffectPreset,period:f64)->f64{
  if period<=0.000_001{return 0.0}
  ((t-e.start_sec).max(0.0)%period+period)%period
}

pub fn period_frames(duration:f64,fps:u32)->Option<u64>{
  if !duration.is_finite()||duration<=0.0||fps==0{return None}
  let exact=duration*fps as f64;
  let rounded=exact.round();
  if rounded<1.0||((exact-rounded).abs()>0.25){return None}
  Some(rounded as u64)
}

fn gcd(mut a:u64,mut b:u64)->u64{while b!=0{let r=a%b;a=b;b=r}a}
fn lcm_bounded(a:u64,b:u64,limit:u64)->Option<u64>{
  if a==0||b==0{return None}
  let q=a/gcd(a,b);
  q.checked_mul(b).filter(|v|*v<=limit)
}

pub fn common_period_frames(periods:&[u64],fps:u32)->Option<u64>{
  if periods.is_empty(){return None}
  let limit=(MAX_FAST_COMMON_PERIOD_SEC*fps.max(1) as f64).round() as u64;
  let mut out=periods[0];
  if out>limit{return None}
  for p in periods.iter().copied().skip(1){out=lcm_bounded(out,p,limit)?;}
  Some(out)
}

pub fn apply_effects_filter(
  mut graph:String,
  mut base:String,
  effects:&[EffectPreset],
  width:u32,
  height:u32,
  fps:u32,
  input_start:usize,
)->(String,String){
  for (n,e) in effects.iter().filter(|e|e.enabled&&!e.source.trim().is_empty()).enumerate(){
    let idx=input_start+n;
    let fx=format!("fx{n}");
    let next=format!("b{}",n+1);
    let opacity=e.opacity.unwrap_or(1.0).clamp(0.0,1.0);
    let target=((width as f64)*e.scale.clamp(0.05,1.5)).round().max(2.0) as u32;
    let target=if target%2==0{target}else{target+1};
    let scale=if e.fullscreen{
      format!("scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black@0")
    }else{
      format!("scale={target}:-2:flags=lanczos")
    };
    let x=if e.fullscreen{"0".into()}else{format!("max(0,min(W-w,W*{}-w/2))",e.x.clamp(0.0,1.0))};
    let y=if e.fullscreen{"0".into()}else{format!("max(0,min(H-h,H*{}-h/2))",e.y.clamp(0.0,1.0))};

    if e.mode=="strict-prealpha"{
      graph.push_str(&format!(";[{idx}:v]fps={},setpts=PTS-STARTPTS,format=rgba,colorchannelmixer=aa={opacity}[{fx}];[{base}]format=rgba[base{n}];[base{n}][{fx}]overlay=x='{x}':y='{y}':shortest=0:repeatlast=1:eof_action=repeat:format=auto[{next}]",fps.max(1)));
      base=next;
      continue
    }
    if e.mode=="strict-screen-cache"{
      let px=if e.fullscreen{"0".into()}else{format!("max(0,min(ow-iw,ow*{}-iw/2))",e.x.clamp(0.0,1.0))};
      let py=if e.fullscreen{"0".into()}else{format!("max(0,min(oh-ih,oh*{}-ih/2))",e.y.clamp(0.0,1.0))};
      graph.push_str(&format!(";[{base}]format=gbrp[base{n}];[{idx}:v]fps={},format=gbrp,pad={width}:{height}:'{px}':'{py}':color=black[{fx}];[base{n}][{fx}]blend=all_mode=screen:all_opacity={opacity}[{next}]",fps.max(1)));
      base=next;
      continue
    }
    if e.mode=="screen"||e.mode=="screen-cache"{
      let px=if e.fullscreen{"0".into()}else{format!("max(0,min(ow-iw,ow*{}-iw/2))",e.x.clamp(0.0,1.0))};
      let py=if e.fullscreen{"0".into()}else{format!("max(0,min(oh-ih,oh*{}-ih/2))",e.y.clamp(0.0,1.0))};
      graph.push_str(&format!(";[{base}]format=gbrp[base{n}];[{idx}:v]fps={},format=gbrp,{scale},pad={width}:{height}:'{px}':'{py}':color=black,setsar=1[{fx}];[base{n}][{fx}]blend=all_mode=screen:all_opacity={opacity}[{next}]",fps.max(1)));
    }else{
      let prepared=if e.mode=="prealpha"{
        format!("[{idx}:v]fps={},format=rgba,{scale}",fps.max(1))
      }else if e.mode=="luma"{
        format!("[{idx}:v]fps={},format=rgba,lumakey=threshold={}:tolerance={}:softness=0.08,{scale}",fps.max(1),e.luma_threshold,e.luma_tolerance)
      }else{
        let (similarity,blend)=cache::chromakey_params_859(e);
        let kind=cache::despill_type(&e.key_color);
        let mix=e.despill.clamp(0.0,1.0);
        format!("[{idx}:v]fps={},{scale},format=rgba,colorkey={}:{}:{},despill=type={kind}:mix={mix}:expand=0.20",fps.max(1),color_ffmpeg(&e.key_color),similarity,blend)
      };
      graph.push_str(&format!(";{prepared},colorchannelmixer=aa={opacity}[{fx}];[{base}]format=rgba[base{n}];[base{n}][{fx}]overlay=x='{x}':y='{y}':shortest=1:eof_action=repeat:format=auto[{next}]"));
    }
    base=next;
  }
  (graph,base)
}

#[cfg(test)]
mod tests{
  use super::*;
  fn effect(mode:&str)->EffectPreset{EffectPreset{
    id:"x".into(),name:"x".into(),source:"/tmp/x.mp4".into(),enabled:true,mode:mode.into(),key_color:"#00ff00".into(),
    similarity:0.18,blend:0.08,despill:0.35,luma_threshold:0.12,luma_tolerance:0.12,saturation:1.0,x:0.5,y:0.5,scale:1.0,fullscreen:true,
    preview_frame_time:0.0,start_sec:0.0,end_sec:None,cache_key:None,cache_ready:None,asset_state:None,asset_error:None,
    usage_mode:Some("always".into()),interval_sec:None,usage_duration_sec:None,target:Some("CUSTOM".into()),offset_x:Some(0.0),offset_y:Some(0.0),opacity:Some(1.0)
  }}
  #[test]
  fn common_period_is_exact_and_bounded(){
    assert_eq!(common_period_frames(&[300],60),Some(300));
    assert_eq!(common_period_frames(&[240,360],60),Some(720));
    assert_eq!(common_period_frames(&[420,660],60),None);
  }
  #[test]
  fn frame_period_rejects_non_frame_aligned_duration(){
    assert_eq!(period_frames(5.0,60),Some(300));
    assert_eq!(period_frames(5.003,60),Some(300));
    assert_eq!(period_frames(5.01,60),None);
  }
  #[test]
  fn fast_periodic_modes_are_allowlisted(){
    assert!(fast_periodic_effect_supported(&effect("screen")));
    assert!(fast_periodic_effect_supported(&effect("chromakey")));
    assert!(fast_periodic_effect_supported(&effect("luma")));
    assert!(!fast_periodic_effect_supported(&effect("screen-cache")));
    assert!(!fast_periodic_effect_supported(&effect("prealpha")));
    assert!(!fast_periodic_effect_supported(&effect("unknown")));
    let mut timed=effect("chromakey");timed.usage_mode=Some("interval".into());assert!(!fast_periodic_effect_supported(&timed));
  }
  #[test]
  fn base_filter_matches_canonical_cover_crop(){
    let f=base_filter("0:v",1920,1080,60);
    assert!(f.contains("force_original_aspect_ratio=increase"));
    assert!(f.contains("crop=1920:1080"));
  }
}
