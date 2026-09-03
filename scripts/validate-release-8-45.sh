#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-}";FFPROBE="${2:-}"
fail(){ echo "❌ ENDLUME 8.45: $1" >&2; exit 1; }
[[ -f src-tauri/src/render.rs ]] || fail "render.rs missing"
[[ -f src/components/VyronBatchBridge.tsx ]] || fail "VYRON bridge missing"
[[ -f src-tauri/src/vyron_bridge.rs ]] || fail "native VYRON bridge missing"
grep -Fq 'struct FinalProbe{video_bitrate:Option<u64>}' src-tauri/src/render.rs || fail "FinalProbe missing"
grep -Fq 'ffprobe_output_timeout' src-tauri/src/render.rs || fail "bounded FFprobe helper missing"
grep -Fq 'Duration::from_secs(12)' src-tauri/src/render.rs || fail "FFprobe deadline missing"
grep -Fq 'final-verify' src-tauri/src/render.rs || fail "final verify timing missing"
grep -Fq 'Финализация результата' src-tauri/src/render.rs || fail "finalization stage missing"
grep -Fq 'last_error.starts_with("FINAL_VERIFY:")' src-tauri/src/render.rs || fail "verification must not trigger full rerender"
if grep -Fq '"-count_packets"' src-tauri/src/render.rs; then fail "full-file FFprobe packet scan survived"; fi
if grep -Fq 'nb_read_packets' src-tauri/src/render.rs; then fail "full-file packet counter survived"; fi
if grep -Fq 'let bitrate=probe_video_bitrate(app,&out).await;' src-tauri/src/render.rs; then fail "second blocking bitrate FFprobe survived"; fi
grep -Fq 'resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};' src-tauri/src/render.rs || fail "30/60 selected render mode changed"
grep -Fq 'fn cfr_output_args(' src-tauri/src/render.rs || fail "CFR helper lost"
grep -Fq '"-fps_mode".into(),"cfr".into()' src-tauri/src/render.rs || fail "CFR output lost"
grep -Fq '"-c:v","copy","-c:a","copy","-video_track_timescale","60000"' src-tauri/src/render.rs || fail "final stream-copy mux changed"
grep -Fq 'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}' src-tauri/src/render.rs || fail "500k size/quality budget changed"
grep -Fq 'force_original_aspect_ratio=increase' src-tauri/src/render.rs || fail "YouTube Fill changed"
grep -Fq 'materialize_continuous_audio' src-tauri/src/render.rs || fail "gapless audio path changed"
grep -Fq 'acrossfade=d={cf}:c1=tri:c2=tri' src-tauri/src/render.rs || fail "crossfade path changed"
grep -Fq '<VyronBatchBridge/>' src/pages/App.tsx || fail "VYRON bridge mount lost"
grep -Fq 'reportVyronRender' src/tauri.ts || fail "VYRON status reporting lost"
if grep -RniE 'googleapis\.com|youtube\.googleapis\.com|openai\.com|api\.anthropic\.com' src/components/VyronBatchBridge.tsx src-tauri/src/vyron_bridge.rs >/dev/null; then fail "external API leaked into local bridge"; fi
[[ -f scripts/validate-motion-ui-8-41.mjs ]] || fail "60 FPS UI validator missing"
node scripts/validate-motion-ui-8-41.mjs
if [[ -n "$FFMPEG" && -x "$FFMPEG" && -n "$FFPROBE" && -x "$FFPROBE" ]]; then
  TMP="$(mktemp -d /tmp/endlume-845-probe.XXXXXX)"; trap 'rm -rf "$TMP"' EXIT
  "$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=black:s=640x360:r=60:d=2' -f lavfi -i 'sine=frequency=440:sample_rate=48000:duration=2' -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -b:a 320k -shortest -y "$TMP/smoke.mp4"
  START=$(python3 - <<'PY'
import time
print(time.monotonic())
PY
)
  "$FFPROBE" -v error -show_entries 'format=duration:stream=codec_type,width,height,r_frame_rate,avg_frame_rate,nb_frames,duration,bit_rate' -of json "$TMP/smoke.mp4" > "$TMP/probe.json"
  END=$(python3 - <<'PY'
import time
print(time.monotonic())
PY
)
  python3 - "$TMP/probe.json" "$START" "$END" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]));elapsed=float(sys.argv[3])-float(sys.argv[2])
assert float(p['format']['duration'])>1.5
assert any(s.get('codec_type')=='video' for s in p['streams'])
assert any(s.get('codec_type')=='audio' for s in p['streams'])
assert elapsed < 5.0, f'metadata FFprobe unexpectedly slow: {elapsed:.3f}s'
print(f'PASS: metadata FFprobe {elapsed:.3f}s')
PY
fi
grep -Fq '"version": "1.0.0-alpha.8.45"' package.json || fail "package version wrong"
grep -Fq '1.0.0-alpha.8.45' src-tauri/tauri.conf.json || fail "Tauri version wrong"
grep -Fq 'studio.endlume.desktop' src-tauri/tauri.conf.json || fail "bundle identifier changed"
echo '✅ ENDLUME 8.45 FAST FINALIZE VALIDATION PASS'
echo '✅ no full-file -count_packets scan'
echo '✅ one bounded final metadata verification path'
echo '✅ verification cannot trigger a second full render'
echo '✅ 8.44 video/audio/Effects/Subscribe/VYRON contracts preserved'
