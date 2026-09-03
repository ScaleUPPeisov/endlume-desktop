#!/usr/bin/env python3
from pathlib import Path
import re, sys

ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd()
VERSION='1.0.0-alpha.8.49'
PRODUCT='ENDLUME STUDIO PEISOV'

def need(rel):
    p=ROOT/rel
    if not p.is_file(): raise SystemExit(f'8.49: missing {rel}')
    return p

def must(cond,msg):
    if not cond: raise SystemExit('8.49: '+msg)

p=need('src-tauri/src/render.rs')
s=p.read_text(encoding='utf-8')

# Exact verified 8.47 foundation. 8.49 is deliberately narrow: fidelity selector,
# whole-track boundary math, persistent short render/audio caches and branding.
for marker in [
    'FFMPEG_STALL_TIMEOUT_SECS:u64=120',
    'ffprobe_output_timeout(app,args,Duration::from_secs(12))',
    'resolved_job.settings.width=1920;',
    'resolved_job.settings.height=1080;',
    'resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};',
    'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}',
    '"-crf","18","-maxrate","500k","-bufsize","4M"',
    '"-c:v","copy","-c:a","copy","-video_track_timescale","60000"',
    'let mut sub_cache:HashMap<String,PathBuf>=HashMap::new();',
    'materialize_continuous_audio',
    'acrossfade=d={cf}:c1=tri:c2=tri',
    'force_original_aspect_ratio=increase',
]: must(marker in s,'8.47 invariant missing: '+marker)

# Cache hashing uses dependencies already present in the app (cache.rs uses them).
if 'use sha2::{Digest,Sha256};' not in s:
    s=s.replace('use serde_json::json;\n','use serde_json::json;\nuse sha2::{Digest,Sha256};\n',1)
s=s.replace('time::{Duration,Instant}};','time::{Duration,Instant,UNIX_EPOCH}};',1)
must('use sha2::{Digest,Sha256};' in s and 'UNIX_EPOCH' in s,'persistent cache imports missing')

# Persistent cache lives on the fast app cache volume. The per-render .ENDLUME-work
# directory can still be deleted safely after every job; expensive reusable units survive.
anchor='fn render_diag_path(job:&QueueJob)->Option<PathBuf>{'
must(anchor in s,'render_diag_path anchor missing')
helpers=r'''const RENDER_CACHE_GENERATION:&str="8.49-fidelity-v1";

fn render_file_stamp(path:&Path)->String{
  let meta=std::fs::metadata(path).ok();
  let size=meta.as_ref().map(|m|m.len()).unwrap_or(0);
  let modified=meta.and_then(|m|m.modified().ok()).and_then(|t|t.duration_since(UNIX_EPOCH).ok()).map(|d|d.as_nanos()).unwrap_or(0);
  format!("{}|{}|{}",path.to_string_lossy(),size,modified)
}

fn render_cache_hash(raw:&str)->String{
  let mut h=Sha256::new();h.update(raw.as_bytes());hex::encode(h.finalize())[..32].to_string()
}

fn render_cache_dir(app:&AppHandle)->Result<PathBuf,String>{
  let dir=app.path().app_cache_dir().map_err(|e|e.to_string())?.join("render-v1-fidelity-849");
  std::fs::create_dir_all(&dir).map_err(|e|format!("Не удалось создать быстрый render cache: {e}"))?;Ok(dir)
}

fn render_cache_ready(path:&Path)->bool{std::fs::metadata(path).map(|m|m.is_file()&&m.len()>1024).unwrap_or(false)}

fn render_audio_cache_key(job:&QueueJob,kind:&str)->String{
  let mut raw=format!("{}|audio|{}|{}x{}|fps{}|codec{}|cf{:.6}|norm{}|",RENDER_CACHE_GENERATION,kind,job.settings.width,job.settings.height,job.settings.fps,job.settings.codec,job.settings.crossfade_sec,job.settings.normalize_lufs);
  for a in &job.project.audio{raw.push_str(&render_file_stamp(Path::new(a)));raw.push('|');}
  if let Some(a)=job.ambient.as_ref(){raw.push_str(&render_file_stamp(Path::new(a)));}
  render_cache_hash(&raw)
}

'''
s=s.replace(anchor,helpers+anchor,1)

# Restore the quality-proven x265-first short-master path. VideoToolbox stays a
# fallback only; 500k budget and CRF18/long-GOP profile are unchanged.
old_choose='''async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{
  #[cfg(target_os="macos")]
  {if attempt==1&&encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  if encoder_works(app,"libx265").await{return "libx265".into()}
  #[cfg(target_os="macos")]
  {if encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  "libx265".into()
}'''
new_choose='''async fn choose_hybrid_encoder(app:&AppHandle,attempt:u32)->String{
  if attempt==1&&encoder_works(app,"libx265").await{return "libx265".into()}
  #[cfg(target_os="macos")]
  {if encoder_works(app,"hevc_videotoolbox").await{return "hevc_videotoolbox".into()}}
  if encoder_works(app,"libx265").await{return "libx265".into()}
  "libx265".into()
}'''
must(old_choose in s,'8.47 hardware-first selector changed unexpectedly')
s=s.replace(old_choose,new_choose,1)

# Whole-track means WHOLE TRACK. Never fall back to the exact 2h target just
# because the next full song extends the result by more than four minutes.
old_duration='fn smart_final_duration(target:f64,durations:&[f64],crossfade:f64,mode:&str)->f64{if mode!="whole-track"||durations.is_empty(){return target}let mut t=0.0;let mut i=0usize;while t<target{let add=(durations[i%durations.len()]-if t>0.0{crossfade}else{0.0}).max(0.1);t+=add;i+=1;}if t-target<=240.0{t}else{target}}'
new_duration='fn smart_final_duration(target:f64,durations:&[f64],crossfade:f64,mode:&str)->f64{if mode!="whole-track"||durations.is_empty(){return target}let cf=crossfade.clamp(0.0,10.0);let mut t=0.0;let mut i=0usize;while t<target{let idx=i%durations.len();let add=(durations[idx]-if idx>0{cf}else{0.0}).max(0.1);t+=add;i+=1;}t}'
must(old_duration in s,'old smart_final_duration not found')
s=s.replace(old_duration,new_duration,1)

audio_tests=r'''

#[cfg(test)]
mod audio_timeline_849_tests{
  use super::smart_final_duration;
  fn tracks()->Vec<f64>{vec![590.125,610.250,605.375,615.500,620.625,595.750,600.875,612.125,608.250,603.375,617.500,621.625]}
  fn near(a:f64,b:f64){assert!((a-b).abs()<0.000_001,"actual={a:.9} expected={b:.9}");}
  #[test]fn whole_track_never_cuts_boundary_song(){let d=tracks();let target=6900.0;let expected=d.iter().sum::<f64>();assert!(expected-target>240.0);near(smart_final_duration(target,&d,0.0,"whole-track"),expected);}
  #[test]fn crossfade_counts_only_real_in_cycle_boundaries(){let d=tracks();let cf=5.125;let expected=d.iter().sum::<f64>()-cf*((d.len()-1) as f64);near(smart_final_duration(6900.0,&d,cf,"whole-track"),expected);}
  #[test]fn stream_loop_boundary_has_no_fake_crossfade(){let d=tracks();let cf=5.125;let first=d.iter().sum::<f64>()-cf*((d.len()-1) as f64);near(smart_final_duration(first+100.0,&d,cf,"whole-track"),first+d[0]);}
  #[test]fn exact_mode_keeps_exact_target(){let d=tracks();near(smart_final_duration(7200.375,&d,5.0,"exact"),7200.375);}
  #[test]fn duration_clamps_crossfade_like_audio_filter(){let d=tracks();let expected=d.iter().sum::<f64>()-10.0*((d.len()-1) as f64);near(smart_final_duration(6900.0,&d,99.0,"whole-track"),expected);}
}
'''
s=s.replace(new_duration,new_duration+audio_tests,1)

# Original MP3 path: first render still validates and performs bitstream-copy;
# later identical playlists reuse that exact validated cycle byte-for-byte.
orig_head='''async fn build_original_audio_cycle(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<(PathBuf,Vec<f64>,f64),String>{
  if job.project.audio.is_empty(){return Err("Нет песен".into())}
'''
must(orig_head in s,'original audio function head missing')
orig_new=orig_head+'''  let original_cache=render_cache_dir(app)?.join(format!("audio-original-{}.mp3",render_audio_cache_key(job,"original")));
  if render_cache_ready(&original_cache){
    let mut durations=Vec::new();for a in &job.project.audio{durations.push(probe_duration(app,a).await.unwrap_or(180.0).max(0.2));}
    let cycle_duration=probe_duration(app,original_cache.to_string_lossy().as_ref()).await.unwrap_or_else(|_|durations.iter().sum::<f64>().max(0.2));
    render_diag(job,"audio-cache",&format!("HIT original {}",original_cache.display()));return Ok((original_cache,durations,cycle_duration))
  }
'''
s=s.replace(orig_head,orig_new,1)
must('let cycle=work.join("audio-original-clean.mp3");' in s,'original audio cycle output marker missing')
s=s.replace('let cycle=work.join("audio-original-clean.mp3");','let cycle=original_cache.clone();',1)

# Crossfade/HQ320 cycle is also persistent. Internal cache files do not need
# faststart; removing that relocation changes no samples and avoids an extra pass.
processed_marker='''  let cycle=work.join("audio-crossfade-gapless.m4a");
  let expected=(durations.iter().sum::<f64>()-cf*((durations.len().saturating_sub(1)) as f64)).max(0.2);'''
processed_new='''  let cycle=render_cache_dir(app)?.join(format!("audio-processed-{}.m4a",render_audio_cache_key(job,"processed-hq320")));
  let expected=(durations.iter().sum::<f64>()-cf*((durations.len().saturating_sub(1)) as f64)).max(0.2);
  if render_cache_ready(&cycle){let cycle_duration=probe_duration(app,cycle.to_string_lossy().as_ref()).await.unwrap_or(expected);render_diag(job,"audio-cache",&format!("HIT processed {}",cycle.display()));return Ok((cycle,durations,cycle_duration))}'''
must(processed_marker in s,'processed audio cycle marker missing')
s=s.replace(processed_marker,processed_new,1)
s=s.replace('args.extend(vec!["-movflags","+faststart","-progress","pipe:1","-y",cycle.to_string_lossy().as_ref()].into_iter().map(String::from));','args.extend(vec!["-progress","pipe:1","-y",cycle.to_string_lossy().as_ref()].into_iter().map(String::from));',1)

# The already gapless materialized HQ track is large; cache it as well so warm
# renders do not rewrite ~hundreds of MB before the final mux.
continuous_head='''async fn materialize_continuous_audio(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,work:&Path,cycle:&Path,final_duration:f64,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<PathBuf,String>{
  let out=work.join("audio-continuous.m4a");'''
continuous_new='''async fn materialize_continuous_audio(app:&AppHandle,job:&QueueJob,started:i64,timer:&Instant,_work:&Path,cycle:&Path,final_duration:f64,encoder:&str,attempt:u32,cancel:&AtomicBool)->Result<PathBuf,String>{
  let raw=format!("{}|audio-continuous|{}|duration={:.6}",RENDER_CACHE_GENERATION,render_file_stamp(cycle),final_duration);
  let out=render_cache_dir(app)?.join(format!("audio-continuous-{}.m4a",render_cache_hash(&raw)));
  if render_cache_ready(&out){render_diag(job,"audio-cache",&format!("HIT continuous {}",out.display()));return Ok(out)}'''
must(continuous_head in s,'continuous audio function head missing')
s=s.replace(continuous_head,continuous_new,1)

# Persistent high-fidelity variant cache. A changed source image, prepared Effect,
# FPS/resolution/codec or encoder changes the hash and invalidates automatically.
variant_marker='''  let out=work.join(format!("variant-{variant_no:03}.mp4"));let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();let input_start;'''
variant_new='''  let out=if smart{
    let state=serde_json::to_string(effects).unwrap_or_default();
    let raw=format!("{}|variant|{}|{}x{}|fps{}|codec{}|duration={:.6}|encoder={}|{}",RENDER_CACHE_GENERATION,render_file_stamp(Path::new(&job.project.media[0])),job.settings.width,job.settings.height,job.settings.fps,job.settings.codec,master_duration,encoder,state);
    let cached=render_cache_dir(app)?.join(format!("variant-{}.mp4",render_cache_hash(&raw)));
    if render_cache_ready(&cached){render_diag(job,"render-cache",&format!("HIT variant {}",cached.display()));return Ok(cached)}cached
  }else{work.join(format!("variant-{variant_no:03}.mp4"))};let mut args:Vec<String>=vec!["-hide_banner","-loglevel","error"].into_iter().map(String::from).collect();let input_start;'''
must(variant_marker in s,'build_variant output marker missing')
s=s.replace(variant_marker,variant_new,1)
variant_tail='run_ffmpeg(app,job,started,timer,args,"Hybrid Fidelity: собираю короткий master",32.0,3.0,master_duration,encoder,attempt,cancel).await?;Ok(out)'
must(variant_tail in s,'build_variant tail missing')
s=s.replace(variant_tail,'run_ffmpeg(app,job,started,timer,args,"Hybrid Fidelity: собираю короткий master",32.0,3.0,master_duration,encoder,attempt,cancel).await?;if smart{render_diag(job,"render-cache",&format!("STORE variant {}",out.display()));}Ok(out)',1)

# Persistent segment cache. When the active base Effect state is empty the base
# image is static, so its phase is irrelevant and recurring Subscribe events can
# reuse one encoded segment even during the FIRST render.
old_branch='''    if active_sub.is_empty(){
      copy_segment(app,job,&variant,vd,a,b-a,&seg,encoder,attempt,cancel,base,span,started,timer).await?;segments.push(seg);
    }else{
      subscribe_done+=1;render_diag(job,"subscribe",&format!("segment {}/{} interval={}/{} start={:.3} duration={:.3} active={}",subscribe_done,subscribe_segments,i+1,intervals.len(),a,b-a,active_sub.len()));
      let phase=(a%vd.max(0.1)).max(0.0);let mut ids=active_sub.iter().map(|e|e.sub.effect.id.clone()).collect::<Vec<_>>();ids.sort();
      let ck=format!("{}|{:.3}|{:.3}|{}",k,phase,b-a,ids.join(","));
      if let Some(existing)=sub_cache.get(&ck){render_diag(job,"subscribe",&format!("REUSE {}/{} cached={}",subscribe_done,subscribe_segments,existing.display()));segments.push(existing.clone());}
      else{render_sub_segment(app,job,&variant,vd,a,b-a,&active_sub,&seg,encoder,attempt,cancel,base,span,started,timer).await?;sub_cache.insert(ck,seg.clone());render_diag(job,"subscribe",&format!("completed {}/{} start={:.3} duration={:.3}",subscribe_done,subscribe_segments,a,b-a));segments.push(seg);}
    }'''
new_branch='''    if active_sub.is_empty(){
      if smart_repeat_project(job){
        let phase=(a%vd.max(0.1)).max(0.0);let phase_key=if active_fx.is_empty(){0.0}else{phase};
        let raw=format!("{}|copy|{}|phase={:.6}|len={:.6}|state={}",RENDER_CACHE_GENERATION,render_file_stamp(&variant),phase_key,b-a,k);
        let cached=render_cache_dir(app)?.join(format!("copy-{}.mp4",render_cache_hash(&raw)));
        if render_cache_ready(&cached){render_diag(job,"render-cache",&format!("HIT copy {}",cached.display()));}
        else{copy_segment(app,job,&variant,vd,a,b-a,&cached,encoder,attempt,cancel,base,span,started,timer).await?;render_diag(job,"render-cache",&format!("STORE copy {}",cached.display()));}
        segments.push(cached);
      }else{copy_segment(app,job,&variant,vd,a,b-a,&seg,encoder,attempt,cancel,base,span,started,timer).await?;segments.push(seg);}
    }else{
      subscribe_done+=1;render_diag(job,"subscribe",&format!("segment {}/{} interval={}/{} start={:.3} duration={:.3} active={}",subscribe_done,subscribe_segments,i+1,intervals.len(),a,b-a,active_sub.len()));
      let phase=(a%vd.max(0.1)).max(0.0);let phase_key=if active_fx.is_empty(){0.0}else{phase};
      let sub_state=active_sub.iter().map(|e|format!("offset={:.6}|{}",(a-e.event_start).max(0.0),serde_json::to_string(&e.sub).unwrap_or_default())).collect::<Vec<_>>().join("||");
      let raw=format!("{}|subscribe|{}|phase={:.6}|len={:.6}|state={}|{}",RENDER_CACHE_GENERATION,render_file_stamp(&variant),phase_key,b-a,k,sub_state);
      let ck=render_cache_hash(&raw);let cached=render_cache_dir(app)?.join(format!("subscribe-{}.mp4",ck));
      if render_cache_ready(&cached){render_diag(job,"subscribe",&format!("HIT {}/{} cached={}",subscribe_done,subscribe_segments,cached.display()));segments.push(cached.clone());sub_cache.insert(ck,cached);}
      else{render_sub_segment(app,job,&variant,vd,a,b-a,&active_sub,&cached,encoder,attempt,cancel,base,span,started,timer).await?;sub_cache.insert(ck,cached.clone());render_diag(job,"subscribe",&format!("STORE {}/{} start={:.3} duration={:.3}",subscribe_done,subscribe_segments,a,b-a));segments.push(cached);}
    }'''
must(old_branch in s,'assemble_visual segment branch changed unexpectedly')
s=s.replace(old_branch,new_branch,1)

# Diagnostics: warm-cache architecture is explicit; quality encoder is no longer
# mislabeled as hardware-first.
s=s.replace('render_diag(job,"performance",&format!("8.47 encoder={} hardware_first={} final_faststart=false target_video_kbps=500",encoder,encoder=="hevc_videotoolbox"));','render_diag(job,"performance",&format!("8.49 encoder={} quality_master={} persistent_cache=true final_faststart=false target_video_kbps=500",encoder,encoder=="libx265"));',1)

# Hard postconditions before writing runtime source.
for marker in [
    'attempt==1&&encoder_works(app,"libx265")',
    'RENDER_CACHE_GENERATION:&str="8.49-fidelity-v1"',
    'HIT variant', 'subscribe-{}.mp4', 'audio-continuous-{}.m4a',
    'let idx=i%durations.len();', 'audio_timeline_849_tests',
    'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}',
    '"-crf","18","-maxrate","500k","-bufsize","4M"',
]: must(marker in s,'postcondition missing: '+marker)
must('if t-target<=240.0{t}else{target}' not in s,'old 240-second song cut cap survived')

p.write_text(s,encoding='utf-8')

# Version sync only; updater endpoint/pubkey/identifier are never rewritten.
for rel in ['package.json','src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src/tauri.ts','src/pages/SettingsPage.tsx','src/pages/App.tsx']:
    x=need(rel);t=x.read_text(encoding='utf-8');t=re.sub(r'1\.0\.0-alpha\.8\.\d+',VERSION,t);x.write_text(t,encoding='utf-8')

# Final requested public name. Internal bundle identifier and updater identity stay
# studio.endlume.desktop so signed in-app updates continue on the same channel.
conf=need('src-tauri/tauri.conf.json');t=conf.read_text(encoding='utf-8')
t=t.replace('"ENDLUME Studio"',f'"{PRODUCT}"')
must('"productName": "ENDLUME STUDIO PEISOV"' in t,'productName rename failed')
must('"identifier": "studio.endlume.desktop"' in t,'bundle identifier changed')
conf.write_text(t,encoding='utf-8')

ui_files=[need('index.html')]
ui_files += [q for q in (ROOT/'src').rglob('*') if q.is_file() and q.suffix.lower() in {'.ts','.tsx','.html'}]
for x in ui_files:
    t=x.read_text(encoding='utf-8')
    t=re.sub(r'ENDLUME(?: Studio| STUDIO)(?! PEISOV)',PRODUCT,t)
    x.write_text(t,encoding='utf-8')

print('ENDLUME 8.49 fidelity + whole-track audio + persistent warm cache + PEISOV branding: PASS')
