#!/usr/bin/env python3
from pathlib import Path
import re, sys

ROOT = Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd()
VERSION='1.0.0-alpha.8.48'

def need(rel):
    p=ROOT/rel
    if not p.is_file(): raise SystemExit(f'8.48: missing {rel}')
    return p

def must(cond,msg):
    if not cond: raise SystemExit('8.48: '+msg)

p=need('src-tauri/src/render.rs')
s=p.read_text(encoding='utf-8')

for marker in [
    'attempt==1&&encoder_works(app,"hevc_videotoolbox")',
    'target_video_kbps=500',
    'FFMPEG_STALL_TIMEOUT_SECS:u64=120',
    'ffprobe_output_timeout(app,args,Duration::from_secs(12))',
    'resolved_job.settings.width=1920;',
    'resolved_job.settings.height=1080;',
    'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}',
    '"-c:v","copy","-c:a","copy","-video_track_timescale","60000"',
]: must(marker in s,'8.47 invariant missing: '+marker)

old='fn smart_final_duration(target:f64,durations:&[f64],crossfade:f64,mode:&str)->f64{if mode!="whole-track"||durations.is_empty(){return target}let mut t=0.0;let mut i=0usize;while t<target{let add=(durations[i%durations.len()]-if t>0.0{crossfade}else{0.0}).max(0.1);t+=add;i+=1;}if t-target<=240.0{t}else{target}}'
new='fn smart_final_duration(target:f64,durations:&[f64],crossfade:f64,mode:&str)->f64{if mode!="whole-track"||durations.is_empty(){return target}let cf=crossfade.clamp(0.0,10.0);let mut t=0.0;let mut i=0usize;while t<target{let idx=i%durations.len();let add=(durations[idx]-if idx>0{cf}else{0.0}).max(0.1);t+=add;i+=1;}t}'
must(old in s,'whole-track duration block changed or already patched')
s=s.replace(old,new,1)

# Normalize only the spelling of the existing audio-filter clamp. This is
# semantically identical Rust and keeps the validator deterministic.
old_cf='let cf=job.settings.crossfade_sec.clamp(0.,10.);'
new_cf='let cf=job.settings.crossfade_sec.clamp(0.0,10.0);'
if old_cf in s:
    s=s.replace(old_cf,new_cf,1)
must(new_cf in s,'existing FFmpeg crossfade clamp missing')

anchor=new+'\n\nasync fn build_long_audio'
must(anchor in s,'build_long_audio anchor missing after duration patch')

tests=r'''

#[cfg(test)]
mod audio_timeline_tests{
  use super::smart_final_duration;

  fn tracks()->Vec<f64>{
    vec![590.125,610.250,605.375,615.500,620.625,595.750,600.875,612.125,608.250,603.375,617.500,621.625]
  }
  fn near(actual:f64,expected:f64){
    assert!((actual-expected).abs()<0.000_001,"actual={actual:.9} expected={expected:.9}");
  }

  #[test]
  fn whole_track_crossfade_off_never_cuts_boundary_track(){
    let d=tracks();
    let target=6900.0;
    let expected=d.iter().sum::<f64>();
    let actual=smart_final_duration(target,&d,0.0,"whole-track");
    assert!(expected-target>240.0,"fixture must exercise removed 240s cap");
    near(actual,expected);
  }

  #[test]
  fn whole_track_crossfade_on_subtracts_only_real_overlaps(){
    let d=tracks();
    let target=6900.0;
    let cf=5.125;
    let expected=d.iter().sum::<f64>()-cf*((d.len()-1) as f64);
    let actual=smart_final_duration(target,&d,cf,"whole-track");
    assert!(expected>=target);
    near(actual,expected);
  }

  #[test]
  fn repeated_cycle_does_not_invent_crossfade_at_stream_loop_boundary(){
    let d=tracks();
    let cf=5.125;
    let first_cycle=d.iter().sum::<f64>()-cf*((d.len()-1) as f64);
    let target=first_cycle+100.0;
    let expected=first_cycle+d[0];
    let actual=smart_final_duration(target,&d,cf,"whole-track");
    near(actual,expected);
  }

  #[test]
  fn non_whole_track_mode_keeps_exact_target_behavior(){
    let d=tracks();
    near(smart_final_duration(7200.375,&d,5.0,"exact"),7200.375);
  }

  #[test]
  fn crossfade_duration_matches_audio_filter_clamp(){
    let d=tracks();
    let target=6900.0;
    let expected=d.iter().sum::<f64>()-10.0*((d.len()-1) as f64);
    near(smart_final_duration(target,&d,99.0,"whole-track"),expected);
  }
}
'''

s=s.replace(anchor,new+tests+'\n\nasync fn build_long_audio',1)

must('if t-target<=240.0{t}else{target}' not in s,'old 240-second truncation cap still present')
must('let cf=crossfade.clamp(0.0,10.0);' in s,'crossfade duration is not aligned with audio filter clamp')
must('let idx=i%durations.len();' in s,'playlist cycle boundary accounting missing')
must('repeated_cycle_does_not_invent_crossfade_at_stream_loop_boundary' in s,'stream-loop crossfade regression missing')
p.write_text(s,encoding='utf-8')

for rel in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    x=need(rel); t=x.read_text(encoding='utf-8'); t=re.sub(r'1\.0\.0-alpha\.8\.\d+',VERSION,t); x.write_text(t,encoding='utf-8')

print('ENDLUME 8.48 whole-track audio duration fix: PASS')
