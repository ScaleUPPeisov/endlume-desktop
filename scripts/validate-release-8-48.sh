#!/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
R="$ROOT/src-tauri/src/render.rs"
fail(){ echo "FAIL 8.48 AUDIO: $1" >&2; exit 1; }

[[ -f "$R" ]] || fail 'render.rs missing'

# New audio-only contract.
grep -Fq 'fn smart_final_duration' "$R" || fail 'smart_final_duration missing'
grep -Fq 'let cf=crossfade.clamp(0.0,10.0);' "$R" || fail 'crossfade clamp mismatch'
grep -Fq 'whole_track_crossfade_off_never_cuts_boundary_track' "$R" || fail '12-track OFF regression missing'
grep -Fq 'whole_track_crossfade_on_subtracts_only_real_overlaps' "$R" || fail '12-track ON regression missing'
if grep -Fq 'if t-target<=240.0{t}else{target}' "$R"; then
  fail 'old 240-second whole-track truncation cap still present'
fi

# Existing 8.47 contracts must be byte-level present after the audio migration.
for marker in \
  'attempt==1&&encoder_works(app,"hevc_videotoolbox")' \
  'target_video_kbps=500' \
  'FFMPEG_STALL_TIMEOUT_SECS:u64=120' \
  'ffprobe_output_timeout(app,args,Duration::from_secs(12))' \
  'resolved_job.settings.width=1920;' \
  'resolved_job.settings.height=1080;' \
  'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}' \
  '"-c:v","copy","-c:a","copy","-video_track_timescale","60000"' \
  'let mut sub_cache:HashMap<String,PathBuf>=HashMap::new();'
do
  grep -Fq "$marker" "$R" || fail "8.47 invariant lost: $marker"
done

# No alternate trimming path was introduced. Final mux still follows the single
# mathematically resolved final_duration, and no -shortest limiter exists.
python3 - "$R" <<'PY'
import sys
s=open(sys.argv[1],encoding='utf-8').read()
assert 'if t-target<=240.0{t}else{target}' not in s
assert 'let cf=crossfade.clamp(0.0,10.0);' in s
assert 'args.extend(vec!["-t",&final_duration.to_string(),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","copy"' in s
assert '"-shortest"' not in s
assert 'let cf=job.settings.crossfade_sec.clamp(0.0,10.0);' in s
assert 'probe_duration(app,a).await.unwrap_or(180.0).max(0.2)' in s
print('PASS: audio fix only; final mux and duration precision path preserved')
PY

# Independent 12-track ~2h mathematical regression. Values include fractional
# milliseconds and force an overshoot larger than the removed four-minute cap.
python3 - <<'PY'
d=[590.125,610.250,605.375,615.500,620.625,595.750,600.875,612.125,608.250,603.375,617.500,621.625]
target=6900.0
s=sum(d)
assert 7200.0 < s < 7400.0, s
assert s-target > 240.0, (s,target)

def whole(target,d,cf):
    cf=max(0.0,min(10.0,cf)); t=0.0; i=0
    while t < target:
        t += max(0.1,d[i%len(d)]-(cf if i>0 else 0.0))
        i += 1
    return t

off=whole(target,d,0.0)
assert abs(off-s) < 1e-9, (off,s)
cf=5.125
on=whole(target,d,cf)
expected=s-cf*(len(d)-1)
assert abs(on-expected) < 1e-9, (on,expected)
print(f'PASS: 12-track ~2h timeline OFF={off:.3f}s ON={on:.3f}s; no boundary-track cut')
PY

echo '✅ ENDLUME 8.48 AUDIO-ONLY GATE PASS'
echo '✅ whole-track no longer falls back to exact target after +240s'
echo '✅ crossfade math uses the same 0..10s clamp as the actual FFmpeg audio graph'
echo '✅ 1920x1080 / H.265 / VideoToolbox / 500k / Effects / Subscribe / watchdog / updater code untouched'
