#!/bin/bash
set -Eeuo pipefail
FFMPEG="${1:-}";FFPROBE="${2:-}"
fail(){ echo "❌ ENDLUME 8.46: $1" >&2; exit 1; }
R=src-tauri/src/render.rs
C=src-tauri/src/cache.rs
Q=src-tauri/src/queue.rs
[[ -f "$R" && -f "$C" && -f "$Q" ]] || fail "render/cache/queue source missing"

# 8.45 finalization remains metadata-only and bounded.
grep -Fq 'ffprobe_output_timeout' "$R" || fail "bounded final FFprobe lost"
grep -Fq 'Duration::from_secs(12)' "$R" || fail "12s final FFprobe deadline lost"
grep -Fq 'last_error.starts_with("FINAL_VERIFY:")' "$R" || fail "validation retry guard lost"
if grep -Fq '"-count_packets"' "$R"; then fail "full-file packet scan returned"; fi
if grep -Fq 'nb_read_packets' "$R"; then fail "full-file packet counter returned"; fi

# 8.46 watchdog / atomic output / diagnostics.
grep -Fq 'FFMPEG_STALL_TIMEOUT_SECS:u64=120' "$R" || fail "120s progress watchdog missing"
grep -Fq 'ffmpeg_is_stalled(last_progress.elapsed())' "$R" || fail "progress timestamp watchdog missing"
grep -Fq 'out_time_us=' "$R" || fail "out_time progress tracking missing"
grep -Fq 'frame=' "$R" || fail "frame progress tracking missing"
grep -Fq 'total_size=' "$R" || fail "size progress tracking missing"
grep -Fq 'RETRY_AFTER_STALL' "$R" || fail "controlled stage retry missing"
grep -Fq 'stage_attempt in 1..=2' "$R" || fail "retry bound missing"
grep -Fq 'last_error.starts_with("FFMPEG_STALL:")' "$R" || fail "stall can still trigger full-project rerender"
grep -Fq 'staged_output(&args)' "$R" || fail "main/helper partial stage output missing"
grep -Fq 'promote_partial(&staged)' "$R" || fail "atomic stage promotion missing"
grep -Fq 'cleanup_partial(&staged)' "$R" || fail "partial cleanup missing"
grep -Fq 'render-diagnostic.log' "$R" || fail "render diagnostic file missing"
grep -Fq 'START pid=' "$R" || fail "FFmpeg START/PID diagnostic missing"
grep -Fq 'PROGRESS pid=' "$R" || fail "FFmpeg progress diagnostic missing"
grep -Fq 'STALL pid=' "$R" || fail "FFmpeg stall diagnostic missing"
grep -Fq 'SUCCESS pid=' "$R" || fail "FFmpeg success diagnostic missing"
grep -Fq 'events={} intervals={} segments={} final_duration=' "$R" || fail "Subscribe plan diagnostic missing"
grep -Fq 'segment {}/{} interval={}/{}' "$R" || fail "Subscribe per-segment diagnostic missing"
grep -Fq 'REUSE {}/{}' "$R" || fail "Subscribe cache reuse diagnostic missing"
grep -Fq 'Visual plan слишком раздроблен' "$R" || fail "visual-segment guard missing"
grep -Fq 'более 2048 событий' "$R" || fail "Subscribe event guard missing"
grep -Fq 'let mut sub_cache:HashMap<String,PathBuf>=HashMap::new();' "$R" || fail "proven Subscribe segment cache optimization lost"
grep -Fq 'mod watchdog_tests' "$R" || fail "watchdog Rust tests missing"

# Verification failure after successful mux must preserve the actual MP4.
grep -Fq 'FINAL_VERIFY_FILE_PRESERVED:' "$R" || fail "valid mux is still deleted after final verification failure"
grep -Fq 'file_preserved=' "$R" || fail "preserved final mux diagnostic missing"
grep -Fq 'Видео создано, но не удалось завершить финальную проверку.' "$Q" || fail "final-verification preserved-file message missing"

# Cache FFmpeg is supervised too.
grep -Fq 'async fn run_cache_ffmpeg(' "$C" || fail "Effects/Subscribe cache watchdog missing"
grep -Fq 'Duration::from_secs(120)' "$C" || fail "cache stall deadline missing"
grep -Fq '"-progress","pipe:1"' "$C" || fail "cache progress channel missing"
grep -Fq '.partial.mov' "$C" || fail "cache partial output missing"
if grep -Fq '.args(args).output().await' "$C"; then fail "unbounded cache FFmpeg survived"; fi
grep -Fq 'FFmpeg остановлен watchdog' "$Q" || fail "friendly queue stall error missing"
grep -Fq '*runtime.active.lock()=None;runtime.persist(&app);' "$Q" || fail "queue active cleanup invariant lost"

# Quality / renderer contracts are immutable in this release.
grep -Fq 'resolved_job.settings.fps=if resolved_job.settings.fps>=50{60}else{30};' "$R" || fail "30/60 mode changed"
grep -Fq 'fn cfr_output_args(' "$R" || fail "CFR helper lost"
grep -Fq '"-fps_mode".into(),"cfr".into()' "$R" || fail "CFR output lost"
grep -Fq '"-c:v","copy","-c:a","copy","-video_track_timescale","60000"' "$R" || fail "final stream-copy mux changed"
grep -Fq 'fn hybrid_video_kbps(_s:&RenderSettings)->u64{500}' "$R" || fail "500k size/quality budget changed"
grep -Fq 'force_original_aspect_ratio=increase' "$R" || fail "YouTube Fill changed"
grep -Fq 'materialize_continuous_audio' "$R" || fail "gapless audio changed"
grep -Fq 'acrossfade=d={cf}:c1=tri:c2=tri' "$R" || fail "crossfade changed"
grep -Fq '<VyronBatchBridge/>' src/pages/App.tsx || fail "VYRON bridge lost"
grep -Fq '@tauri-apps/plugin-updater' package.json || fail "native updater lost"

# Identity.
grep -Fq '"version": "1.0.0-alpha.8.46"' package.json || fail "package version wrong"
grep -Fq '1.0.0-alpha.8.46' src-tauri/tauri.conf.json || fail "Tauri version wrong"
grep -Fq 'studio.endlume.desktop' src-tauri/tauri.conf.json || fail "bundle id changed"

# Rust watchdog semantics are actually compiled/executed, not only grepped.
(cd src-tauri && cargo test watchdog_tests --lib)

# Sidecar-level verification: metadata probe is quick and .partial -> final works.
if [[ -n "$FFMPEG" && -x "$FFMPEG" && -n "$FFPROBE" && -x "$FFPROBE" ]]; then
  TMP="$(mktemp -d /tmp/endlume-846-gate.XXXXXX)"; trap 'rm -rf "$TMP"' EXIT
  "$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'color=c=black:s=640x360:r=60:d=4' -f lavfi -i 'sine=frequency=440:sample_rate=48000:duration=4' -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -b:a 320k -shortest -y "$TMP/sample.partial.mp4"
  test -s "$TMP/sample.partial.mp4"
  mv "$TMP/sample.partial.mp4" "$TMP/sample.mp4"
  START=$(python3 -c 'import time;print(time.monotonic())')
  "$FFPROBE" -v error -show_entries 'format=duration:stream=codec_type,width,height,r_frame_rate,avg_frame_rate,nb_frames,duration,bit_rate' -of json "$TMP/sample.mp4" > "$TMP/probe.json"
  END=$(python3 -c 'import time;print(time.monotonic())')
  python3 - "$TMP/probe.json" "$START" "$END" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]));elapsed=float(sys.argv[3])-float(sys.argv[2])
assert float(p['format']['duration'])>3.5
assert any(s.get('codec_type')=='video' for s in p['streams'])
assert any(s.get('codec_type')=='audio' for s in p['streams'])
assert elapsed < 5.0, elapsed
print(f'PASS: bounded metadata probe fixture {elapsed:.3f}s')
PY
fi

echo '✅ ENDLUME 8.46 RENDER PIPELINE STABILITY GATE PASS'
echo '✅ progress-aware watchdog + exactly one same-stage retry + atomic outputs'
echo '✅ Subscribe plan/segment/PID diagnostics + sub_cache preserved'
echo '✅ helper/cache FFmpeg bounded; final mux preserved on verification-only failure'
echo '✅ 8.45 metadata-only final FFprobe preserved; no whole-project rerender'
echo '✅ quality/audio/FPS/VYRON/updater contracts preserved'
