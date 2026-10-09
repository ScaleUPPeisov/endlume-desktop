use crate::model::EffectPreset;

pub const MAX_FAST_COMMON_PERIOD_SEC:f64=30.0;

fn color_ffmpeg(hex:&str)->String{
  format!("0x{}",hex.trim().trim_start_matches('#').trim_start_matches("0x"))
}

pub fn base_filter(label:&str,width:u32,height:u32,fps:u32)->String{
  format!("[{label}]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={},setsar=1",fps.max(1))
}

pub fn active_effects_at(effects:&[EffectPreset],t:f64,final_duration:f64)->Vec<EffectPreset>{
  effects.iter().filter(|e|{
    e.enabled
      && !e.source.trim().is_empty()
      && e.start_sec<=t+0.000_001
      && e.end_sec.unwrap_or(final_duration)>t
  }).cloned().collect()
}

pub fn fast_periodic_effect_supported(e:&EffectPreset)->bool{
  e.enabled
    && !e.source.trim().is_empty()
    && e.start_sec.abs()<=0.000_1
    && e.end_sec.is_none()
    && matches!(e.mode.as_str(),"screen"|"screen-cache"|"chromakey"|"luma"|"prealpha")
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
    if e.mode=="screen"||e.mode=="screen-cache"{
      let prep=if e.mode=="screen-cache"{
        format!("[{idx}:v]fps={},scale={width}:{height},setsar=1",fps.max(1))
      }else{
        format!("[{idx}:v]fps={},scale={width}:{height},setsar=1,eq=saturation={}",fps.max(1),e.saturation)
      };
      graph.push_str(&format!(";{prep}[{fx}];[{base}][{fx}]blend=all_mode=screen:all_opacity=1[{next}]"));
    }else{
      let prep=if e.mode=="prealpha"{
        format!("[{idx}:v]fps={},format=argb",fps.max(1))
      }else if e.mode=="luma"{
        format!("[{idx}:v]fps={},format=rgba,eq=saturation={},lumakey=threshold={}:tolerance={}:softness=0.08",fps.max(1),e.saturation,e.luma_threshold,e.luma_tolerance)
      }else{
        format!("[{idx}:v]fps={},format=rgba,chromakey={}:{}:{}",fps.max(1),color_ffmpeg(&e.key_color),e.similarity.max(0.00001),e.blend)
      };
      let scale=if e.fullscreen{format!("scale={width}:{height}")}else{format!("scale=iw*{}:ih*{}",e.scale.max(0.01),e.scale.max(0.01))};
      let x=if e.fullscreen{"0".into()}else{format!("(W-w)*{}",e.x.clamp(0.0,1.0))};
      let y=if e.fullscreen{"0".into()}else{format!("(H-h)*{}",e.y.clamp(0.0,1.0))};
      graph.push_str(&format!(";{prep},{scale}[{fx}];[{base}][{fx}]overlay=x='{x}':y='{y}':shortest=1:eof_action=repeat[{next}]"));
    }
    base=next;
  }
  (graph,base)
}

#[cfg(test)]
mod tests{
  use super::*;
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
}
