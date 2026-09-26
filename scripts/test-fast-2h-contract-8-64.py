#!/usr/bin/env python3
from pathlib import Path
import re

render=Path("src-tauri/src/render.rs").read_text(encoding="utf-8")
manifest=Path("src-tauri/src/mp4_manifest.rs").read_text(encoding="utf-8")
license_rs=Path("src-tauri/src/license.rs").read_text(encoding="utf-8")
client=Path("supabase/functions/endlume-client-api/index.ts").read_text(encoding="utf-8")

def section(text,start,end):
    a=text.index(start)
    b=text.find(end,a+len(start))
    return text[a:] if b<0 else text[a:b]

decision=section(render,"pub(crate) fn fast_path_decision","async fn choose_fidelity_encoder")
assert 'reason:"FAST_ONE_IMAGE"' in decision
assert 'reason:"FAST_MULTI_STILL"' in decision
assert 'DISQUALIFIED_MULTI_STILL_EFFECTS' in decision
assert 'DISQUALIFIED_MULTI_STILL_SUBSCRIBE' in decision
assert 'job.project.media.iter().all(|m|is_image(m))' in decision

multi=section(render,"async fn render_multi_still_zero_copy_863","async fn render_zero_sub_zero_copy_856")
assert "PHYSICAL_FRAMES_PER_STILL:usize=30" in multi
assert "LOGICAL_FRAMES_PER_STILL:usize=600" in multi
assert 'crate::mp4_manifest::remap_video_samples(&seed,&seed,&selected)?' in multi
assert '"-c:v","copy","-c:a","copy"' in multi
assert 'Fast Original Audio • MP3 packet-copy' in multi
assert 'strict_856_validate_natural_size(out)?' in multi
assert 'stream_loop' in multi, "audio loop is expected; final video payload must come from sample-table remap"
# Video pool is finite; there must be no -stream_loop before the first video input.
before_audio=multi[:multi.index("match audio")]
assert '"-stream_loop","-1","-i",physical' not in before_audio

render_job=section(render,"pub async fn render_job","fn natural_key")
assert 'resolved_job.settings.crossfade_sec=0.0;' not in render_job
assert 'resolved_job.settings.normalize_lufs=false;' not in render_job
assert 'resolved_job.ambient=None;' not in render_job
assert 'audio_processing_requested(job)' in render_job
assert 'let processed=processed_audio;' in render_job
assert 'render_multi_still_zero_copy_863' in render_job
assert 'unique_output(&out_dir,&job.project.name)' in render_job, "fast result must remain Ready Videos.mp4"
assert 'unique_output_ext(&out_dir,&job.project.name,"mov")' not in render_job
assert 'fast-863-multistill-seed.mp4' in render, "multi-still manifest seed must be MP4"
assert 'strict-856-seed.mp4' in render, "one-image manifest seed must be MP4"
assert render_job.index("render_multi_still_zero_copy_863") < render_job.index("render_zero_sub_zero_copy_856")
assert 'audio_mode:if processed_audio{"PROCESSED_AUDIO".into()}else{"ORIGINAL_MP3_PACKET_COPY".into()}' in render_job
assert 'verify_strict_857_result(app,&out,final_duration,!processed_audio)' in render_job

original=section(render,"async fn build_original_audio_cycle","async fn build_lossless_audio_cycle")
assert original.count('"-c:a","copy"') >= 2
for forbidden in ('"-c:a","aac"','"-c:a","alac"','"-c:a","pcm'):
    assert forbidden not in original, forbidden

strict_verify=section(render,"async fn verify_strict_857_result","#[derive(Clone)]")
assert 'bytes>700_000_000' not in strict_verify
assert 'STRICT_856_MAX_BYTES' not in render
assert 'file-size ranges are targets' in render
assert 'codec_name' in strict_verify and 'Some("hevc")' in strict_verify
assert 'audio_codec!="mp3"' in strict_verify
assert 'audio_codec!="aac"' in strict_verify
assert '(expected*0.5)' in strict_verify, "middle seek must be validated for video/audio"
assert 'track_durations[0]' in strict_verify and 'boundary+0.20' in strict_verify, "first song transition must be physically seek/decode validated"
assert '(expected-10.0)' in strict_verify, "last 10 seconds must be covered by targeted audio validation"

for forbidden in ("STRICT_856_PAD_TARGET_BYTES",'f.write_all(b"free")',"set_len(current+add)"):
    assert forbidden not in render, f"synthetic padding returned: {forbidden}"

assert "pub fn remap_video_samples" in manifest
assert "pub fn expand_video_prefix_cycle" in manifest
assert "rebuild_video_trak" in manifest
assert "multistill_sample_schedule_math" in manifest

hybrid=section(render,"async fn choose_hybrid_encoder","fn strict_856_encoder_allowed")
order=[hybrid.index(x) for x in ['"hevc_nvenc"','"hevc_qsv"','"hevc_amf"']]
assert order==sorted(order), order
assert '"libx265"' in hybrid

assert 'fn audio_processing_requested' in render
processed_audio=section(render,"async fn build_lossless_processed_audio_cycle","async fn materialize_continuous_audio")
assert 'loudnorm=I=-14:TP=-1.5:LRA=11' in processed_audio, "Processed Audio must apply requested LUFS normalization"
assert 'amix=inputs=2:duration=first' in processed_audio, "Processed Audio must apply requested ambient mix"
assert '"-stream_loop","-1","-i",a.as_str()' in processed_audio, "Processed Audio ambient input must loop safely"
assert 'smart_repeat_project(job)&&!audio_processing_requested(job)' in render and 'raw_eta.map(|v|v.min(30.0))' in render, "30s ETA cap must apply only to Fast Original Audio"
for timing in ("scan","encoder-benchmark","image-preprocess","visual-master","audio-mux","manifest-expand","finalize","ffprobe-validation","total"):
    assert f'"{timing}"' in render, f"stage timing missing {timing}"

for field in (
    "render_wall_seconds","final_video_duration_seconds","fast_path",
    "fast_path_reason","audio_mode","video_codec","audio_codec",
    "media_count","image_count","video_count"
):
    assert field in license_rs, f"license telemetry missing {field}"
    assert field in client, f"server telemetry missing {field}"

# Terminal events must preserve the last encoder if a legacy client omits it.
assert 'textField("encoder",body.encoder,80)' in client
assert 'encoder: body.encoder == null ? null' not in client




# 8.64 Turbo additions: cached bounded-parallel audio probes, direct concat-list packet-copy,
# measured Windows HEVC selection, richer stage telemetry and full-window updater UX.
assert 'AUDIO_PROBE_CACHE' in render
assert 'probe_audio_meta' in render
assert 'stream=codec_name,sample_rate,channels:format=duration' in render
assert 'audioDirectConcatList' in render
assert 'AudioSource::ConcatList' in render
assert 'do not physically copy the whole playlist before the final MP4 mux' in render
assert '"-f","concat","-safe","0"' in original
assert 'PARALLEL_PROBES:usize=4' in render
assert 'probe_original_audio_batch' in render
assert 'audio-original-direct.mp3' not in original, "8.64 fast path must not materialize the whole playlist before final mux"
assert 'Direct MP3 concat не прошёл integrity gate' in original
assert 'FFMPEG_LAUNCHES' in render and 'FFPROBE_LAUNCHES' in render
assert '"physicalEncodedFrames"' in render and '"logicalFrames"' in render and '"manifestFrames"' in render
for timing in ("project-scan","audio-probe","audio-preparation","encoder-detection","validation","side-files"):
    assert f'"{timing}"' in render, f"8.64 timing missing {timing}"

bench=Path("src-tauri/src/benchmark.rs").read_text(encoding="utf-8")
for encoder in ("hevc_nvenc","hevc_qsv","hevc_amf","libx265"):
    assert encoder in bench, f"HEVC benchmark candidate missing {encoder}"
assert 'fast_encoder_sample' in render
assert 'best:Option<(String,f64)>' in render
assert 'encoder-selection-8.64.json' in render
assert 'Win32_VideoController' in render and 'DriverVersion' in render
assert 'load_persistent_encoder' in render and 'save_persistent_encoder' in render
assert 'invalidate_hybrid_encoder_cache' in render

app=Path("src/pages/App.tsx").read_text(encoding="utf-8")
ux=Path("src/components/EndlumeUpdateExperience.tsx").read_text(encoding="utf-8")
style=Path("src/update-experience.css").read_text(encoding="utf-8")
updater=Path("src-tauri/src/updater_windows.rs").read_text(encoding="utf-8")
assert Path("src/assets/endlume-homer.png").is_file(), "Homer local asset missing"
assert "StartupSplash" in app and "UpdateExperience" in app and "PostUpdateNotice" in app
assert "../assets/endlume-homer.png" in ux
for state_name in ("DOWNLOADING","VERIFYING","READY_TO_INSTALL","INSTALLING","RESTART_REQUIRED","FAILED"):
    assert state_name in updater, f"updater state missing {state_name}"
for field in ("downloaded_bytes","total_bytes","bytes_per_second","eta_seconds"):
    assert field in updater, f"real transfer telemetry missing {field}"
assert "SHA-256" in updater
assert ".endlumeUpdateExperience" in style and ".endlumeStartup" in style

# Version surface must be physically 8.64 everywhere used by the package manager.
import json
assert json.loads(Path("package.json").read_text())["version"]=="1.0.0-alpha.8.64"
assert json.loads(Path("src-tauri/tauri.conf.json").read_text())["version"]=="1.0.0-alpha.8.64"
cargo=Path("src-tauri/Cargo.toml").read_text()
assert re.search(r'^version\s*=\s*"1\.0\.0-alpha\.8\.64"$',cargo,re.M)

print("ENDLUME_FAST_TURBO_CONTRACT_864_GREEN")
