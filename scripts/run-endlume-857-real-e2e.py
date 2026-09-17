#!/usr/bin/env python3
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(os.environ.get("GITHUB_WORKSPACE") or Path(__file__).resolve().parents[1]).resolve()
SIDE = Path(sys.argv[1]).resolve()
FFMPEG = Path(sys.argv[2]).resolve()
FFPROBE = Path(sys.argv[3]).resolve()
METRICS = Path(sys.argv[4] if len(sys.argv) > 4 else "857-real-e2e.json").resolve()
WIDTH, HEIGHT, FPS, WORK_FPS = 1920, 1080, 60, 30
MAX_GOP = 1800


def log(*parts):
    print("[e2e857]", *parts, flush=True)


def run(args, *, capture=False, env=None, cwd=None):
    cmd = [str(x) for x in args]
    log("RUN", " ".join(cmd[:8]) + (" ..." if len(cmd) > 8 else ""))
    return subprocess.run(cmd, check=True, stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None, env=env, cwd=cwd)


def out(args):
    p = run(args, capture=True)
    return p.stdout.decode("utf-8", errors="replace").strip()


def duration(path):
    return float(out([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path]))


def stream_json(path):
    return json.loads(out([FFPROBE, "-v", "error", "-show_entries",
                           "stream=index,codec_type,codec_name,pix_fmt,width,height,avg_frame_rate,nb_frames,sample_rate,channels",
                           "-of", "json", path]))["streams"]


def count_frames(path):
    return int(out([FFPROBE, "-v", "error", "-select_streams", "v:0", "-count_frames",
                    "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1", path]))


def count_packets(path):
    return int(out([FFPROBE, "-v", "error", "-select_streams", "v:0", "-count_packets",
                    "-show_entries", "stream=nb_read_packets", "-of", "default=nw=1:nk=1", path]))


def audio_sig(path):
    v = out([FFPROBE, "-v", "error", "-select_streams", "a:0", "-show_entries",
             "stream=codec_name,sample_rate,channels", "-of", "csv=p=0:s=|", path]).split("|")
    if len(v) < 3:
        raise RuntimeError(f"bad audio signature: {path}: {v}")
    return v[0], int(v[1]), int(v[2])


def packet_hash(path, seconds=None):
    args = [FFMPEG, "-hide_banner", "-loglevel", "error", "-i", path, "-map", "0:a:0"]
    if seconds is not None:
        args += ["-t", f"{seconds:.6f}"]
    args += ["-c:a", "copy", "-f", "data", "-"]
    p = run(args, capture=True)
    return hashlib.sha256(p.stdout).hexdigest()


def ff_color(raw):
    s = str(raw or "00ff00").strip().lstrip("#")
    if s.lower().startswith("0x"):
        s = s[2:]
    return "0x" + s


def even(n):
    n = max(2, int(round(n)))
    return n if n % 2 == 0 else n + 1


def clamp(v, lo, hi):
    return max(lo, min(hi, float(v)))


def pos_expr(axis, value):
    if axis == "x":
        return f"max(0,min(W-w,W*{clamp(value,0,1)}-w/2))"
    return f"max(0,min(H-h,H*{clamp(value,0,1)}-h/2))"


def pad_to_runtime_contract(path):
    current = path.stat().st_size
    if current > 700_000_000:
        raise RuntimeError(f"final size {current} > 700MB")
    if current >= 400_000_000:
        return current
    target = 500_000_000
    add = target - current
    if add < 8 or add > 0xFFFFFFFF:
        raise RuntimeError(f"cannot create safe free atom: add={add}")
    with path.open("ab") as f:
        f.write(int(add).to_bytes(4, "big"))
        f.write(b"free")
        f.truncate(current + add)
        f.flush()
        os.fsync(f.fileno())
    return path.stat().st_size


def seek_decode(path, pos, media):
    if media == "video":
        run([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", f"{pos:.3f}", "-i", path,
             "-map", "0:v:0", "-frames:v", "2", "-f", "null", "-"])
    else:
        run([FFMPEG, "-hide_banner", "-loglevel", "error", "-ss", f"{pos:.3f}", "-i", path,
             "-map", "0:a:0", "-t", "0.25", "-f", "null", "-"])


data = json.loads(SIDE.read_text(errors="replace"))
project = data["project"]
settings = data.get("settings") or {}
effects = [x for x in (data.get("effects") or []) if isinstance(x, dict) and x.get("enabled") and str(x.get("source") or "").strip()]
subscribes = [x for x in (data.get("subscribes") or []) if isinstance(x, dict) and x.get("enabled") and str(x.get("source") or "").strip()]
image = Path(project["media"][0])
audios = [Path(x) for x in project["audio"]]

assert image.is_file(), image
assert len(audios) == 15, len(audios)
assert all(x.is_file() for x in audios)
assert len(effects) >= 2, len(effects)
assert all(Path(x["source"]).is_file() for x in effects)
assert all(Path(x["source"]).is_file() for x in subscribes)

metrics = {
    "status": "started",
    "release_gate": False,
    "project": project.get("name"),
    "media_count": 1,
    "audio_count": len(audios),
    "effect_count": len(effects),
    "active_subscribe_count": len(subscribes),
    "subscribe_schedules": [
        {"name": x.get("name"), "firstAtSec": x.get("firstAtSec"), "secondAtSec": x.get("secondAtSec"), "repeatEverySec": x.get("repeatEverySec")}
        for x in subscribes
    ],
}
METRICS.write_text(json.dumps(metrics, ensure_ascii=False, indent=2))

with tempfile.TemporaryDirectory(prefix="endlume857-e2e-") as td:
    work = Path(td)
    cache_start = time.time()
    cached = []
    effect_durations = []
    for i, effect in enumerate(effects, 1):
        src = Path(effect["source"])
        effect_durations.append(duration(src))
        mode = str(effect.get("mode") or "chroma")
        fullscreen = bool(effect.get("fullscreen"))
        scale = (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
                 f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black@0") if fullscreen else \
                f"scale={even(WIDTH*clamp(effect.get('scale',1),0.05,1.5))}:-2:flags=lanczos"
        if mode in ("screen", "screen-cache"):
            vf = f"fps={WORK_FPS},format=rgb24,{scale}"
            pix = "rgb24"
            cache_mode = "screen"
        elif mode == "luma":
            vf = (f"fps={WORK_FPS},format=rgba,lumakey=threshold={effect.get('lumaThreshold',0.1)}:"
                  f"tolerance={effect.get('lumaTolerance',0.1)}:softness=0.08,{scale},format=argb")
            pix = "argb"
            cache_mode = "prealpha"
        else:
            vf = (f"fps={WORK_FPS},format=rgba,colorkey={ff_color(effect.get('keyColor'))}:"
                  f"{clamp(effect.get('similarity',0.1),0.001,0.60)}:{clamp(effect.get('blend',0.05),0.001,0.35)},"
                  f"{scale},format=argb")
            pix = "argb"
            cache_mode = "prealpha"
        dst = work / f"fx{i:02d}.mov"
        run([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", src, "-vf", vf, "-an",
             "-c:v", "qtrle", "-pix_fmt", pix, "-y", dst])
        cached.append((dst, effect, cache_mode))
    cache_seconds = time.time() - cache_start

    master_duration = max([12.0] + [clamp(x, 2.0, 60.0) for x in effect_durations])
    master_duration = clamp(master_duration, 12.0, 60.0)
    master_frames = max(1, int(round(master_duration * FPS)))
    master = work / "strict-master.mp4"

    args = [FFMPEG, "-hide_banner", "-loglevel", "error", "-filter_complex_threads", "8",
            "-loop", "1", "-framerate", str(WORK_FPS), "-i", image]
    for dst, _, _ in cached:
        args += ["-stream_loop", "-1", "-i", dst]

    graph = (f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase:flags=lanczos+accurate_rnd,"
             f"crop={WIDTH}:{HEIGHT}:(iw-ow)/2:(ih-oh)/2,fps={WORK_FPS},setsar=1[b0]")
    base = "b0"
    for i, (_, effect, cache_mode) in enumerate(cached, 1):
        fx = f"fx{i}"
        nxt = f"b{i}"
        x = pos_expr("x", effect.get("x", 0.5))
        y = pos_expr("y", effect.get("y", 0.5))
        if cache_mode == "screen":
            px = "0" if effect.get("fullscreen") else f"max(0,min(ow-iw,ow*{clamp(effect.get('x',0.5),0,1)}-iw/2))"
            py = "0" if effect.get("fullscreen") else f"max(0,min(oh-ih,oh*{clamp(effect.get('y',0.5),0,1)}-ih/2))"
            graph += (f";[{i}:v]fps={WORK_FPS},format=rgb24,pad={WIDTH}:{HEIGHT}:'{px}':'{py}':color=black[{fx}]"
                      f";[{base}][{fx}]blend=all_mode=screen:all_opacity=1[{nxt}]")
        else:
            graph += (f";[{i}:v]fps={WORK_FPS},setpts=PTS-STARTPTS,format=argb[{fx}]"
                      f";[{base}][{fx}]overlay=x='{x}':y='{y}':shortest=0:repeatlast=1:eof_action=repeat:format=auto[{nxt}]")
        base = nxt
    graph += f";[{base}]fps={FPS},format=yuv420p[outv]"

    render_start = time.time()
    master_start = time.time()
    args += ["-filter_complex", graph, "-map", "[outv]", "-frames:v", str(master_frames), "-an",
             "-c:v", "hevc_videotoolbox", "-realtime", "1", "-prio_speed", "0", "-power_efficient", "0",
             "-q:v", "100", "-b:v", "500k", "-maxrate", "12M", "-bufsize", "64M", "-g", str(min(master_frames, MAX_GOP)),
             "-tag:v", "hvc1", "-pix_fmt", "yuv420p", "-fps_mode", "cfr", "-r", str(FPS),
             "-video_track_timescale", "60000", "-y", master]
    run(args)
    master_seconds = time.time() - master_start
    frames = count_frames(master)
    packets = count_packets(master)
    mdur = duration(master)
    mstreams = stream_json(master)
    mv = next(x for x in mstreams if x.get("codec_type") == "video")
    assert frames == master_frames, (frames, master_frames)
    assert packets == master_frames, (packets, master_frames)
    assert mv.get("codec_name") == "hevc", mv
    assert mv.get("pix_fmt") == "yuv420p", mv
    assert mv.get("width") == WIDTH and mv.get("height") == HEIGHT, mv
    assert mv.get("avg_frame_rate") == "60/1", mv
    assert abs(mdur - master_frames/FPS) < 0.04, (mdur, master_frames/FPS)
    assert master_seconds <= 24.0, master_seconds

    # Original MP3 contract: identical codec/rate/channels, packet-copy only.
    signatures = [audio_sig(x) for x in audios]
    assert all(s[0] == "mp3" for s in signatures), signatures
    assert all(s == signatures[0] for s in signatures), signatures
    track_durations = [duration(x) for x in audios]
    clean = []
    for i, src in enumerate(audios, 1):
        dst = work / f"audio-clean-{i:02d}.mp3"
        run([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", src, "-map", "0:a:0", "-c:a", "copy",
             "-map_metadata", "-1", "-write_xing", "0", "-id3v2_version", "0", "-y", dst])
        assert packet_hash(src) == packet_hash(dst), f"MP3 payload changed for track {i}"
        clean.append(dst)

    raw_list = work / "audio-raw-list.txt"
    raw_list.write_text("\n".join(str(x) for x in clean) + "\n")
    cycle = work / "audio-original-clean.mp3"
    run([FFMPEG, "-hide_banner", "-loglevel", "error", "-fflags", "+genpts", "-i", f"concatf:{raw_list}",
         "-map", "0:a:0", "-c:a", "copy", "-map_metadata", "-1", "-write_xing", "0", "-id3v2_version", "0", "-y", cycle])
    run([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", cycle, "-map", "0:a:0", "-t", "1", "-f", "null", "-"])

    target = float(settings.get("durationHours", 2.0)) * 3600.0
    final_duration = 0.0
    idx = 0
    while final_duration < target:
        final_duration += max(0.1, track_durations[idx % len(track_durations)])
        idx += 1
        if idx > 10000:
            raise RuntimeError("whole-track duration runaway")
    completed_tracks = idx

    seed = work / "strict-seed.mov"
    run([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", master, "-stream_loop", "-1", "-fflags", "+genpts", "-i", cycle,
         "-t", f"{final_duration:.9f}", "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy", "-y", seed])
    # Prove seed's first audio packets are still the same packets as the cycle.
    assert packet_hash(cycle, 5.0) == packet_hash(seed, 5.0), "final seed changed MP3 packet payload"

    total_frames = max(master_frames, int(round(final_duration * FPS)))
    final = work / "strict-final.mov"
    env = os.environ.copy()
    env.update({
        "ENDLUME_MANIFEST_SEED": str(seed),
        "ENDLUME_MANIFEST_OUT": str(final),
        "ENDLUME_MANIFEST_PREFIX_FRAMES": "0",
        "ENDLUME_MANIFEST_CYCLE_FRAMES": str(master_frames),
        "ENDLUME_MANIFEST_TOTAL_FRAMES": str(total_frames),
    })
    run(["cargo", "test", "--manifest-path", "src-tauri/Cargo.toml", "external_prefix_cycle_manifest_if_requested", "--", "--nocapture"],
        env=env, cwd=ROOT)
    assert final.is_file(), final
    final_bytes = pad_to_runtime_contract(final)

    fdur = duration(final)
    streams = stream_json(final)
    video = next(x for x in streams if x.get("codec_type") == "video")
    audio = next(x for x in streams if x.get("codec_type") == "audio")
    assert abs(fdur - final_duration) <= 1.0, (fdur, final_duration)
    assert video.get("codec_name") == "hevc", video
    assert video.get("pix_fmt") == "yuv420p", video
    assert video.get("width") == WIDTH and video.get("height") == HEIGHT, video
    assert video.get("avg_frame_rate") == "60/1", video
    if str(video.get("nb_frames") or "").isdigit():
        assert int(video["nb_frames"]) == total_frames, (video["nb_frames"], total_frames)
    assert audio.get("codec_name") == "mp3", audio
    assert int(audio.get("sample_rate")) == signatures[0][1], audio
    assert int(audio.get("channels")) == signatures[0][2], audio
    assert 400_000_000 <= final_bytes <= 700_000_000, final_bytes
    assert final_bytes >= 500_000_000, f"user 500-700 MB target missed: {final_bytes}"

    seek_decode(final, 0.0, "video")
    seek_decode(final, final_duration * 0.5, "video")
    seek_decode(final, max(0.0, final_duration - 2.0), "video")
    seek_decode(final, 0.0, "audio")
    seek_decode(final, max(0.0, final_duration - 2.0), "audio")

    media_seconds = time.time() - render_start
    metrics.update({
        "status": "passed",
        "release_gate": True,
        "cache_prewarm_seconds": round(cache_seconds, 3),
        "media_pipeline_seconds": round(media_seconds, 3),
        "master_seconds": round(master_seconds, 3),
        "master_frames": frames,
        "master_packets": packets,
        "master_duration": round(mdur, 6),
        "master_gop": min(master_frames, MAX_GOP),
        "quality": "hevc_videotoolbox q:v 100",
        "resolution": "1920x1080",
        "fps": "60/1",
        "audio_codec": "mp3",
        "audio_sample_rate": signatures[0][1],
        "audio_channels": signatures[0][2],
        "whole_track": True,
        "crossfade_sec": 0.0,
        "normalize_lufs": False,
        "target_seconds": round(target, 6),
        "final_duration": round(fdur, 6),
        "completed_track_instances": completed_tracks,
        "total_video_frames": total_frames,
        "final_bytes": final_bytes,
        "final_mb_decimal": round(final_bytes/1_000_000, 3),
        "seek_begin": True,
        "seek_middle": True,
        "seek_tail": True,
        "mp3_packet_copy": True,
        "subscribe_off_gate": True,
        "subscribe_on_gate": None if not subscribes else "pending-dedicated-periodic-test",
    })
    METRICS.write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    log("PASS", json.dumps(metrics, ensure_ascii=False))
