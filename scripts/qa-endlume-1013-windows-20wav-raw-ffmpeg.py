#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psutil

if len(sys.argv) != 4:
    raise SystemExit("usage: qa-endlume-1013-windows-20wav-raw-ffmpeg.py <ffmpeg.exe> <ffprobe.exe> <report-dir>")

ffmpeg = Path(sys.argv[1]).resolve()
ffprobe = Path(sys.argv[2]).resolve()
report_dir = Path(sys.argv[3]).resolve()
report_dir.mkdir(parents=True, exist_ok=True)

for binary in (ffmpeg, ffprobe):
    if not binary.is_file():
        raise SystemExit(f"missing binary: {binary}")

root = Path(tempfile.mkdtemp(prefix="endlume-1013-20wav-"))
fixtures = root / "fixtures"
fixtures.mkdir(parents=True, exist_ok=True)


def run_checked(args, stdout_path=None, stderr_path=None):
    p = subprocess.run([str(x) for x in args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if stdout_path:
        Path(stdout_path).write_text(p.stdout, encoding="utf-8", errors="replace")
    if stderr_path:
        Path(stderr_path).write_text(p.stderr, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {subprocess.list2cmdline([str(x) for x in args])}\n{p.stderr[-4000:]}")
    return p


version = run_checked([ffmpeg, "-hide_banner", "-version"]).stdout
filters = run_checked([ffmpeg, "-hide_banner", "-filters"]).stdout
(report_dir / "ffmpeg-version.txt").write_text(version, encoding="utf-8", errors="replace")
(report_dir / "ffmpeg-filters.txt").write_text(filters, encoding="utf-8", errors="replace")

required_filters = ["aresample", "aformat", "acrossfade", "loudnorm", "alimiter", "concat"]
missing_filters = [name for name in required_filters if name not in filters]
if missing_filters:
    raise SystemExit(f"production FFmpeg missing filters: {missing_filters}")

# Historical ENDLUME QA originally used a 26 second WAV before the 10.0.12
# acceptance case was weakened to 4 seconds and crossfade=0. Restore the
# historically relevant duration so requested 10 second crossfade is not clamped.
base_wav = fixtures / "base-26s-s16le-48k-stereo.wav"
run_checked([
    ffmpeg, "-hide_banner", "-loglevel", "error",
    "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000:duration=26",
    "-ac", "2", "-c:a", "pcm_s16le", "-y", base_wav,
])

tracks = []
for i in range(20):
    track = fixtures / f"track-{i:02}.wav"
    shutil.copy2(base_wav, track)
    tracks.append(track)


def make_graph(crossfade: float, normalize_lufs: bool):
    graph = []
    for i in range(len(tracks)):
        graph.append(
            f"[{i}:a]aresample=48000:async=1:first_pts=0,"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"asetpts=N/SR/TB[a{i}]"
        )

    if len(tracks) == 1:
        last = "a0"
    elif crossfade > 0.01:
        cur = "a0"
        for i in range(1, len(tracks)):
            out = f"xf{i}"
            graph.append(f"[{cur}][a{i}]acrossfade=d={crossfade}:c1=tri:c2=tri[{out}]")
            cur = out
        last = cur
    else:
        inputs = "".join(f"[a{i}]" for i in range(len(tracks)))
        graph.append(f"{inputs}concat=n={len(tracks)}:v=0:a=1[joined]")
        last = "joined"

    music = "processed_music"
    if normalize_lufs:
        graph.append(f"[{last}]loudnorm=I=-14:TP=-1.5:LRA=11[{music}]")
    else:
        graph.append(f"[{last}]anull[{music}]")
    graph.append(f"[{music}]aresample=48000:async=1:first_pts=0,alimiter=limit=0.98[outa]")
    return ";".join(graph)


def run_case(name: str, crossfade: float, normalize_lufs: bool):
    case_dir = report_dir / name
    case_dir.mkdir(parents=True, exist_ok=True)
    graph = make_graph(crossfade, normalize_lufs)
    output = case_dir / "processed-audio.m4a"

    args = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-filter_complex_threads", "4"]
    for track in tracks:
        args += ["-i", str(track)]
    args += [
        "-filter_complex", graph,
        "-map", "[outa]",
        "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-ac", "2",
        "-progress", "pipe:1", "-y", str(output),
    ]

    (case_dir / "filter-complex.txt").write_text(graph + "\n", encoding="utf-8")
    (case_dir / "command.txt").write_text(subprocess.list2cmdline(args) + "\n", encoding="utf-8")

    started = time.perf_counter()
    proc = subprocess.Popen(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process = psutil.Process(proc.pid)
    peak_rss = 0
    samples = []
    while proc.poll() is None:
        try:
            rss = process.memory_info().rss
            peak_rss = max(peak_rss, rss)
            samples.append({"t": round(time.perf_counter() - started, 3), "rssBytes": rss})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        time.sleep(0.1)
    stdout, stderr = proc.communicate()
    wall = time.perf_counter() - started

    (case_dir / "stdout.txt").write_text(stdout or "", encoding="utf-8", errors="replace")
    (case_dir / "stderr.txt").write_text(stderr or "", encoding="utf-8", errors="replace")
    (case_dir / "memory-samples.json").write_text(json.dumps(samples, indent=2) + "\n", encoding="utf-8")

    probe = None
    if output.is_file() and output.stat().st_size > 0:
        q = subprocess.run([
            str(ffprobe), "-v", "error",
            "-show_entries", "stream=codec_type,codec_name,sample_rate,channels:format=duration,size",
            "-of", "json", str(output),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if q.returncode == 0:
            try:
                probe = json.loads(q.stdout)
            except json.JSONDecodeError:
                probe = {"raw": q.stdout}
        else:
            probe = {"error": q.stderr, "exitCode": q.returncode}
        (case_dir / "ffprobe.json").write_text(json.dumps(probe, indent=2) + "\n", encoding="utf-8")

    expected_duration = 26.0 * len(tracks) - (crossfade * (len(tracks) - 1) if crossfade > 0.01 else 0.0)
    return {
        "name": name,
        "crossfadeSec": crossfade,
        "normalizeLufs": normalize_lufs,
        "exitCode": proc.returncode,
        "wallSeconds": round(wall, 3),
        "peakFfmpegRssBytes": peak_rss,
        "expectedCycleDurationSeconds": expected_duration,
        "outputExists": output.is_file(),
        "outputBytes": output.stat().st_size if output.is_file() else 0,
        "probe": probe,
        "stderrTail": (stderr or "")[-8000:],
    }


cases = [
    ("cf0-lufs-off", 0.0, False),
    ("cf5-lufs-off", 5.0, False),
    ("cf10-lufs-off", 10.0, False),
    ("cf5-lufs-on", 5.0, True),
    ("cf10-lufs-on", 10.0, True),
]

results = []
for case in cases:
    try:
        results.append(run_case(*case))
    except Exception as exc:
        results.append({"name": case[0], "crossfadeSec": case[1], "normalizeLufs": case[2], "exception": repr(exc), "exitCode": -999})

machine = {
    "platform": sys.platform,
    "osName": os.name,
    "cpuCount": os.cpu_count(),
    "totalRamBytes": psutil.virtual_memory().total,
}
summary = {
    "kind": "ENDLUME_1013_WINDOWS_20WAV_RAW_FFMPEG_RCA",
    "sourceHead": "c700adb0fa38a5a3a7d448952a6a164fd06cc9ff",
    "machine": machine,
    "ffmpegVersionFirstLine": version.splitlines()[0] if version.splitlines() else "unknown",
    "fixture": {"trackCount": 20, "secondsPerTrack": 26, "codec": "pcm_s16le", "sampleRate": 48000, "channels": 2},
    "results": results,
}
summary["status"] = "GREEN" if all(r.get("exitCode") == 0 for r in results) else "RED"
(report_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False))

# A RED result is intentional RCA evidence, but the workflow should become red so it
# cannot be mistaken for product acceptance. Artifacts are uploaded with if: always().
raise SystemExit(0 if summary["status"] == "GREEN" else 1)
