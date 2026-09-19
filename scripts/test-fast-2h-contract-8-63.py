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
assert render_job.index("render_multi_still_zero_copy_863") < render_job.index("render_zero_sub_zero_copy_856")
assert 'audio_mode:if processed_audio{"PROCESSED_AUDIO".into()}else{"ORIGINAL_MP3_PACKET_COPY".into()}' in render_job
assert 'verify_strict_857_result(app,&out,final_duration,!processed_audio)' in render_job

original=section(render,"async fn build_original_audio_cycle","async fn build_lossless_audio_cycle")
assert original.count('"-c:a","copy"') >= 2
for forbidden in ('"-c:a","aac"','"-c:a","alac"','"-c:a","pcm'):
    assert forbidden not in original, forbidden

strict_verify=section(render,"async fn verify_strict_857_result","#[derive(Clone)]")
assert 'bytes>700_000_000' in strict_verify
assert 'bytes<500_000_000' not in strict_verify
assert 'codec_name' in strict_verify and 'Some("hevc")' in strict_verify
assert 'audio_codec!="mp3"' in strict_verify
assert 'audio_codec!="aac"' in strict_verify
assert '(expected*0.5)' in strict_verify, "middle seek must be validated for video/audio"

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
assert 'raw_eta.map(|v|v.min(30.0))' in render, "fast ETA must not extrapolate into multi-minute values"
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

print("ENDLUME_FAST_2H_CONTRACT_863_GREEN")
