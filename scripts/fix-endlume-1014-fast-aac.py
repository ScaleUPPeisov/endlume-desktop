#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'src-tauri'/'src'/'fast_render.rs'
text=path.read_text(encoding='utf-8')

# Phase-3 originally packet-copied MP3 into MP4. That violates the current
# ENDLUME Apple-compatible final contract (AAC-LC / mp4a / 48 kHz / stereo).
# Keep the zero-copy VIDEO timeline, but encode the AUDIO stream with Apple's
# AudioToolbox AAC encoder. If aac_at is unavailable/fails, try_render_job()
# already falls back to the canonical renderer, so correctness wins.

repls={
    'static-subscribe-hevc-mp3-packet-copy':'static-subscribe-hevc-aac-lc-320k',
    'static-hevc-mp3-packet-copy':'static-hevc-aac-lc-320k',
    'periodic-hevc-mp3-packet-copy':'periodic-hevc-aac-lc-320k',
    'hevc_videotoolbox + MP3 packet-copy ({})':'hevc_videotoolbox + AAC-LC 320k ({})',
    'audio_mode:"mp3-packet-copy".into()':'audio_mode:"aac-lc-320k".into()',
    'audio_codec:"mp3".into()':'audio_codec:"aac".into()',
}
for old,new in repls.items():
    if old in text:
        text=text.replace(old,new)

# Subscribe fast mux: encode MP3 concat input to AAC-LC instead of copying it.
old='''"-fps_mode","cfr","-r",fps.as_str(),"-c:a","copy","-video_track_timescale","60000","-y",out.to_string_lossy().as_ref()'''
new='''"-fps_mode","cfr","-r",fps.as_str(),"-c:a","aac_at","-b:a","320k","-aac_at_mode","cvbr","-aac_at_quality","2","-ar","48000","-ac","2","-tag:a","mp4a","-disposition:a:0","default","-metadata:s:a:0","language=und","-video_track_timescale","60000","-y",out.to_string_lossy().as_ref()'''
if old in text:
    if text.count(old)!=1: raise SystemExit(f'fast_render.rs: subscribe audio-copy anchor count={text.count(old)}')
    text=text.replace(old,new,1)
elif '"-c:a","aac_at","-b:a","320k"' not in text:
    raise SystemExit('fast_render.rs: subscribe AAC patch anchor missing')

# Non-Subscribe fast mux: same AAC contract while video remains packet-copy.
old='''"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy","-video_track_timescale","60000","-y",out.to_string_lossy().as_ref()'''
new='''"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac_at","-b:a","320k","-aac_at_mode","cvbr","-aac_at_quality","2","-ar","48000","-ac","2","-tag:a","mp4a","-disposition:a:0","default","-metadata:s:a:0","language=und","-video_track_timescale","60000","-y",out.to_string_lossy().as_ref()'''
if old in text:
    if text.count(old)!=1: raise SystemExit(f'fast_render.rs: normal audio-copy anchor count={text.count(old)}')
    text=text.replace(old,new,1)
elif text.count('"-c:a","aac_at","-b:a","320k"')<2:
    raise SystemExit('fast_render.rs: normal AAC patch anchor missing')

# Make the fast renderer's own verification enforce the same final audio contract.
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

# No production fast mux is allowed to advertise/return MP3 anymore.
for forbidden in ['audio_mode:"mp3-packet-copy"','audio_codec:"mp3"','MP3 stream-copy missing']:
    if forbidden in text: raise SystemExit(f'fast_render.rs: forbidden legacy contract remains: {forbidden}')

path.write_text(text,encoding='utf-8')
print('PASS: Phase-3 fast renderer keeps zero-copy HEVC video but enforces AAC-LC 320k / 48k / stereo final audio')
