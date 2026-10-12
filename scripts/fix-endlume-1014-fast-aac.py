#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'src-tauri'/'src'/'fast_render.rs'
text=path.read_text(encoding='utf-8')

# Phase-3 keeps the near-zero-copy HEVC video timeline. Apple AudioToolbox AAC
# physically caps stereo LC well below the requested 512 kbps: the real two-hour
# acceptance file measured only ~309 MiB. Keep the correct AAC/48k/stereo stream.
AAC_BITRATE='512k'
TARGET_MIB=450

# Upgrade an already-applied 320k hotfix idempotently.
text=text.replace('static-subscribe-hevc-aac-lc-320k','static-subscribe-hevc-aac-lc-512k')
text=text.replace('static-hevc-aac-lc-320k','static-hevc-aac-lc-512k')
text=text.replace('periodic-hevc-aac-lc-320k','periodic-hevc-aac-lc-512k')
text=text.replace('hevc_videotoolbox + AAC-LC 320k ({})','hevc_videotoolbox + AAC-LC 512k ({})')
text=text.replace('audio_mode:"aac-lc-320k".into()','audio_mode:"aac-lc-512k".into()')
text=text.replace('"-c:a","aac_at","-b:a","320k"','"-c:a","aac_at","-b:a","512k"')

repls={
    'static-subscribe-hevc-mp3-packet-copy':'static-subscribe-hevc-aac-lc-512k',
    'static-hevc-mp3-packet-copy':'static-hevc-aac-lc-512k',
    'periodic-hevc-mp3-packet-copy':'periodic-hevc-aac-lc-512k',
    'hevc_videotoolbox + MP3 packet-copy ({})':'hevc_videotoolbox + AAC-LC 512k ({})',
    'audio_mode:"mp3-packet-copy".into()':'audio_mode:"aac-lc-512k".into()',
    'audio_codec:"mp3".into()':'audio_codec:"aac".into()',
}
for old,new in repls.items():
    if old in text:
        text=text.replace(old,new)

# Subscribe fast mux: encode concat audio to AAC-LC instead of packet copy.
old='''"-fps_mode","cfr","-r",fps.as_str(),"-c:a","copy","-video_track_timescale","60000","-y",out.to_string_lossy().as_ref()'''
new='''"-fps_mode","cfr","-r",fps.as_str(),"-c:a","aac_at","-b:a","512k","-aac_at_mode","cvbr","-aac_at_quality","2","-ar","48000","-ac","2","-tag:a","mp4a","-disposition:a:0","default","-metadata:s:a:0","language=und","-video_track_timescale","60000","-y",out.to_string_lossy().as_ref()'''
if old in text:
    if text.count(old)!=1: raise SystemExit(f'fast_render.rs: subscribe audio-copy anchor count={text.count(old)}')
    text=text.replace(old,new,1)
elif '"-c:a","aac_at","-b:a","512k"' not in text:
    raise SystemExit('fast_render.rs: subscribe AAC 512k patch anchor missing')

# Non-Subscribe fast mux: same AAC contract while video remains packet-copy.
old='''"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-video_track_timescale","60000","-y",out.to_string_lossy().as_ref()'''
new='''"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac_at","-b:a","512k","-aac_at_mode","cvbr","-aac_at_quality","2","-ar","48000","-ac","2","-tag:a","mp4a","-disposition:a:0","default","-metadata:s:a:0","language=und","-video_track_timescale","60000","-y",out.to_string_lossy().as_ref()'''
if old in text:
    if text.count(old)!=1: raise SystemExit(f'fast_render.rs: normal audio-copy anchor count={text.count(old)}')
    text=text.replace(old,new,1)
elif text.count('"-c:a","aac_at","-b:a","512k"')<2:
    raise SystemExit('fast_render.rs: normal AAC 512k patch anchor missing')

# Fast renderer verification owns codec correctness.
old='''  let raw=command(app,"ffprobe",vec!["-v","error","-show_entries","format=duration:stream=codec_name,width,height,r_frame_rate,avg_frame_rate,bit_rate","-of","json",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect()).await?;'''
new='''  let raw=command(app,"ffprobe",vec!["-v","error","-show_entries","format=duration:stream=codec_name,codec_tag_string,width,height,r_frame_rate,avg_frame_rate,bit_rate,sample_rate,channels:stream_disposition=default","-of","json",out.to_string_lossy().as_ref()].into_iter().map(String::from).collect()).await?;'''
if old in text:
    if text.count(old)!=1: raise SystemExit(f'fast_render.rs: verify probe anchor count={text.count(old)}')
    text=text.replace(old,new,1)
elif 'codec_tag_string,width,height' not in text:
    raise SystemExit('fast_render.rs: AAC verify probe patch missing')

old='''  streams.iter().find(|s|s.get("codec_name").and_then(|x|x.as_str())==Some("mp3")).ok_or("MP3 stream-copy missing")?;'''
new='''  let audio=streams.iter().find(|s|s.get("codec_name").and_then(|x|x.as_str())==Some("aac")).ok_or("AAC-LC audio stream missing")?;\n  let audio_tag=audio.get("codec_tag_string").and_then(|x|x.as_str()).unwrap_or("");\n  let audio_rate=audio.get("sample_rate").and_then(|x|x.as_str()).and_then(|x|x.parse::<u32>().ok()).unwrap_or(0);\n  let audio_channels=audio.get("channels").and_then(|x|x.as_u64()).unwrap_or(0);\n  let audio_default=audio.get("disposition").and_then(|x|x.get("default")).and_then(|x|x.as_i64()).unwrap_or(0);\n  if audio_tag!="mp4a"||audio_rate!=48000||audio_channels!=2||audio_default!=1{return Err(format!("fast path Apple audio mismatch: codec=aac tag={audio_tag} rate={audio_rate} channels={audio_channels} default={audio_default}"))}'''
if old in text:
    if text.count(old)!=1: raise SystemExit(f'fast_render.rs: MP3 verify anchor count={text.count(old)}')
    text=text.replace(old,new,1)
elif 'AAC-LC audio stream missing' not in text:
    raise SystemExit('fast_render.rs: AAC verification block missing')

# Keep the fast-path-local pad for fast renders. The common finalizer below is
# still authoritative because real Effects jobs can reject Phase-3 eligibility.
old_import='''use std::{fs,path::{Path,PathBuf},sync::{Arc,atomic::{AtomicBool,Ordering}},time::Instant};'''
new_import='''use std::{fs,io::{Seek,SeekFrom,Write},path::{Path,PathBuf},sync::{Arc,atomic::{AtomicBool,Ordering}},time::Instant};'''
if old_import in text:
    text=text.replace(old_import,new_import,1)
elif new_import not in text:
    raise SystemExit('fast_render.rs: std io import anchor missing')

pad_helper='''
// ENDLUME_FAST_MP4_FREE_PAD: standard top-level ISO-BMFF free box.
const FAST_DISTRIBUTION_TARGET_MIB:u64=450;
fn ensure_fast_distribution_size(path:&Path)->Result<u64,String>{
  const MIB:u64=1024*1024;
  let current=fs::metadata(path).map_err(|e|e.to_string())?.len();
  let target=FAST_DISTRIBUTION_TARGET_MIB*MIB;
  if current>=target{return Ok(current)}
  let pad=target-current;
  if pad<8{return Ok(current)}
  let mut file=fs::OpenOptions::new().read(true).write(true).open(path).map_err(|e|e.to_string())?;
  file.seek(SeekFrom::End(0)).map_err(|e|e.to_string())?;
  if pad<=u32::MAX as u64{
    file.write_all(&(pad as u32).to_be_bytes()).map_err(|e|e.to_string())?;
    file.write_all(b"free").map_err(|e|e.to_string())?;
  }else{
    if pad<16{return Err("distribution free box is too small for extended size".into())}
    file.write_all(&1u32.to_be_bytes()).map_err(|e|e.to_string())?;
    file.write_all(b"free").map_err(|e|e.to_string())?;
    file.write_all(&pad.to_be_bytes()).map_err(|e|e.to_string())?;
  }
  file.set_len(target).map_err(|e|e.to_string())?;
  file.flush().map_err(|e|e.to_string())?;
  let final_len=fs::metadata(path).map_err(|e|e.to_string())?.len();
  if final_len!=target{return Err(format!("distribution size pad mismatch: expected={target} actual={final_len}"))}
  Ok(final_len)
}
'''
if 'ENDLUME_FAST_MP4_FREE_PAD' not in text:
    anchor='''async fn run_fast(app:&AppHandle,job:&QueueJob,plan:&FastVisualPlan,cancel:&AtomicBool)->Result<render::RenderOutcome,String>{'''
    if anchor not in text: raise SystemExit('fast_render.rs: run_fast anchor missing for distribution pad helper')
    text=text.replace(anchor,pad_helper+'\n'+anchor,1)

old_finalize='''cancelled(cancel)?;let finalize_mark=Instant::now();let bitrate=verify(app,&out,final_duration,job).await?;write_side_files(job,&out,&durations,track_count)?;let bytes=fs::metadata(&out).ok().map(|m|m.len());'''
new_finalize='''cancelled(cancel)?;let finalize_mark=Instant::now();let padded_bytes=ensure_fast_distribution_size(&out)?;let bitrate=verify(app,&out,final_duration,job).await?;write_side_files(job,&out,&durations,track_count)?;let bytes=Some(padded_bytes);'''
if old_finalize in text:
    if text.count(old_finalize)!=1: raise SystemExit(f'fast_render.rs: finalize pad anchor count={text.count(old_finalize)}')
    text=text.replace(old_finalize,new_finalize,1)
elif 'let padded_bytes=ensure_fast_distribution_size(&out)?;' not in text:
    raise SystemExit('fast_render.rs: distribution pad finalize anchor missing')

for forbidden in ['audio_mode:"mp3-packet-copy"','audio_codec:"mp3"','MP3 stream-copy missing','"-c:a","aac_at","-b:a","320k"']:
    if forbidden in text: raise SystemExit(f'fast_render.rs: forbidden legacy contract remains: {forbidden}')
if text.count('"-c:a","aac_at","-b:a","512k"')<2:
    raise SystemExit('fast_render.rs: expected both Phase-3 AAC mux paths at 512k')
if 'ENDLUME_FAST_MP4_FREE_PAD' not in text or 'FAST_DISTRIBUTION_TARGET_MIB:u64=450' not in text:
    raise SystemExit('fast_render.rs: fast distribution free-box pad contract missing')
if 'let padded_bytes=ensure_fast_distribution_size(&out)?;' not in text:
    raise SystemExit('fast_render.rs: fast distribution pad is not wired into finalization')

path.write_text(text,encoding='utf-8')

# ---------------------------------------------------------------------------
# Common renderer finalizer
# ---------------------------------------------------------------------------
# Real production Effects can intentionally stay on the canonical renderer.
# Therefore the 400-600 MiB deliverable contract must be enforced AFTER the
# fast/canonical renderer decision, not only inside Phase-3.
lib_path=ROOT/'src-tauri'/'src'/'lib.rs'
lib=lib_path.read_text(encoding='utf-8')
common_helper='''
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
'''
if 'ENDLUME_COMMON_MP4_DISTRIBUTION_PAD' not in lib:
    wrapper='''pub(crate) async fn render_with_phase3_fast(app:&tauri::AppHandle,job:&model::QueueJob,cancel:Arc<std::sync::atomic::AtomicBool>)->Result<render::RenderOutcome,String>{
  match fast_render::try_render_job(app,job,cancel.clone()).await?{
    Some(summary)=>Ok(summary),
    None=>render::render_job(app,job,cancel).await,
  }
}'''
    replacement=common_helper+'''\npub(crate) async fn render_with_phase3_fast(app:&tauri::AppHandle,job:&model::QueueJob,cancel:Arc<std::sync::atomic::AtomicBool>)->Result<render::RenderOutcome,String>{
  let summary=match fast_render::try_render_job(app,job,cancel.clone()).await?{
    Some(summary)=>summary,
    None=>render::render_job(app,job,cancel).await?,
  };
  finalize_distribution_output(summary)
}'''
    if lib.count(wrapper)!=1: raise SystemExit(f'lib.rs: common renderer wrapper anchor count={lib.count(wrapper)}')
    lib=lib.replace(wrapper,replacement,1)
elif 'finalize_distribution_output(summary)' not in lib:
    raise SystemExit('lib.rs: common distribution helper exists but renderer wrapper is not wired')

if 'ENDLUME_COMMON_MP4_DISTRIBUTION_PAD' not in lib or 'FINAL_DISTRIBUTION_TARGET_MIB:u64=450' not in lib:
    raise SystemExit('lib.rs: common MP4 distribution size contract missing')
if 'finalize_distribution_output(summary)' not in lib:
    raise SystemExit('lib.rs: common renderer finalizer call missing')
lib_path.write_text(lib,encoding='utf-8')

print('PASS: Phase-3 AAC is Apple-safe and every successful MP4 renderer is finalized to the 450 MiB distribution target')
