#!/usr/bin/env python3
from pathlib import Path
s = Path('src-tauri/src/render.rs').read_text(encoding='utf-8')
required = [
    'ENDLUME_WINDOWS_861_STRICT_ENCODERS',
    'for encoder in ["hevc_nvenc","hevc_qsv","hevc_amf"]',
    'matches!(encoder,"hevc_nvenc"|"hevc_qsv"|"hevc_amf"|"libx265")',
    'let max_attempts=if smart_repeat_project(job){if cfg!(target_os="windows"){2}else{1}}else{2};',
    'choose_hybrid_encoder(app,attempt).await',
    '"hevc_nvenc"=>vec!["-c:v","hevc_nvenc"',
    '"hevc_qsv"=>vec!["-c:v","hevc_qsv"',
    '"hevc_amf"=>vec!["-c:v","hevc_amf"',
    '"libx265"=>{',
    '"-fps_mode","cfr","-r","60","-video_track_timescale","60000"',
    'expand_video_prefix_cycle',
    'build_original_audio_cycle',
    'finalize_local_output',
]
for needle in required:
    assert needle in s, f'missing Windows 8.61 contract: {needle}'
# macOS remains first-party strict path; Windows port must not delete it.
assert 'encoder=="hevc_videotoolbox"' in s
# The old unconditional smart-repeat VideoToolbox rejection must be gone.
assert 'software fallback отключён' not in s
assert 'медленный software fallback запрещён' not in s
print('ENDLUME_WINDOWS_861_STRICT_PORT_GREEN')
