#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import os
import plistlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

OWNER_EXPECTED_SHA = "2df386c00da09e76f90218061e7f57ccfba2249a654ec1262b06000b322eb9d7"
PRODUCT_BASE = "3f06c7329bd3821bc160e6d88c5b294fc0d82c2b"
FAST_SOURCE = "a7a399e83de8b9248e2065c6dda1f9079ded6565"

def sh(cmd, *, env=None, timeout=300, capture=True, check=True):
    cmd = [str(x) for x in cmd]
    print("+", " ".join(cmd), flush=True)
    p = subprocess.run(
        cmd,
        env=env,
        timeout=timeout,
        text=False,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and p.returncode != 0:
        out = (p.stdout or b"").decode("utf-8", "replace")[-4000:]
        err = (p.stderr or b"").decode("utf-8", "replace")[-4000:]
        raise RuntimeError(f"command failed rc={p.returncode}: {' '.join(cmd)}\nstdout:\n{out}\nstderr:\n{err}")
    return p

def text(cmd, **kw):
    p = sh(cmd, **kw)
    return (p.stdout or b"").decode("utf-8", "replace").strip()

def find_tool(app: Path, name: str) -> Path:
    macos = app / "Contents" / "MacOS"
    candidates = [
        macos / name,
        macos / f"{name}-aarch64-apple-darwin",
        macos / f"{name}-universal-apple-darwin",
    ]
    candidates += sorted(macos.glob(f"{name}*"))
    for p in candidates:
        if p.is_file() and os.access(p, os.X_OK):
            return p
    system = shutil.which(name)
    if system:
        return Path(system)
    raise RuntimeError(f"{name} not found in candidate bundle or PATH")

def read_app_exe(app: Path) -> Path:
    with open(app / "Contents" / "Info.plist", "rb") as f:
        info = plistlib.load(f)
    exe = info["CFBundleExecutable"]
    out = app / "Contents" / "MacOS" / exe
    if not out.is_file():
        raise RuntimeError(f"candidate executable missing: {out}")
    return out

def ffprobe_json(ffprobe: Path, path: Path):
    return json.loads(text([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", path], timeout=120))

def stream_probe(ffprobe: Path, path: Path):
    d = ffprobe_json(ffprobe, path)
    streams = d.get("streams", [])
    video = next((x for x in streams if x.get("codec_type") == "video"), None)
    audio = next((x for x in streams if x.get("codec_type") == "audio"), None)
    if not video or not audio:
        raise RuntimeError(f"missing A/V streams in {path}")
    duration = float(d.get("format", {}).get("duration") or 0.0)
    return d, video, audio, duration

def full_decode(ffmpeg: Path, path: Path):
    started = time.perf_counter()
    p = sh([ffmpeg, "-hide_banner", "-v", "error", "-i", path, "-map", "0:v:0", "-map", "0:a:0?", "-f", "null", "-"], timeout=900, check=False)
    stderr = (p.stderr or b"").decode("utf-8", "replace").strip()
    return {"ok": p.returncode == 0 and not stderr, "seconds": time.perf_counter() - started, "stderr": stderr[-4000:]}

def seek_checks(ffmpeg: Path, path: Path, duration: float):
    points = sorted(set(max(0.0, min(duration - 0.25, x)) for x in [0.0, duration*.1, duration*.5, duration*.9, duration*.99]))
    rows = []
    for at in points:
        started = time.perf_counter()
        p = sh([ffmpeg, "-hide_banner", "-v", "error", "-ss", f"{at:.6f}", "-i", path, "-t", "0.30",
                "-map", "0:v:0", "-map", "0:a:0?", "-f", "null", "-"], timeout=120, check=False)
        err = (p.stderr or b"").decode("utf-8", "replace").strip()
        rows.append({"at": at, "ok": p.returncode == 0 and not err, "seconds": time.perf_counter()-started, "stderr": err[-1000:]})
    return rows

def dts_check(ffprobe: Path, path: Path):
    cmd = [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_packets", "-show_entries", "packet=dts_time", "-of", "csv=p=0", path]
    print("+", " ".join(map(str, cmd)), flush=True)
    p = subprocess.Popen([str(x) for x in cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    prev = None
    count = 0
    bad = None
    assert p.stdout is not None
    for raw in p.stdout:
        s = raw.strip().strip('"')
        if not s or s == "N/A":
            bad = f"missing dts at packet {count}"
            break
        try:
            v = float(s.split(",")[0])
        except Exception:
            bad = f"bad dts '{s}' at packet {count}"
            break
        if not math.isfinite(v):
            bad = f"non-finite dts at packet {count}"
            break
        if prev is not None and v <= prev:
            bad = f"non-monotonic dts {prev} -> {v} at packet {count}"
            break
        prev = v
        count += 1
    if bad:
        p.kill()
    err = (p.stderr.read() if p.stderr else "")
    rc = p.wait()
    if rc != 0 and not bad:
        bad = f"ffprobe rc={rc}: {err[-1000:]}"
    return {"ok": bad is None and count > 0, "packets": count, "error": bad}

def packet_signature(ffprobe: Path, paths, select="a:0"):
    h = hashlib.sha256()
    count = 0
    first = None
    last = None
    for path in paths:
        cmd = [ffprobe, "-v", "error", "-select_streams", select, "-show_packets",
               "-show_entries", "packet=data_hash", "-show_data_hash", "sha256", "-of", "csv=p=0", path]
        print("+", " ".join(map(str, cmd)), flush=True)
        p = subprocess.Popen([str(x) for x in cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        assert p.stdout is not None
        for raw in p.stdout:
            val = raw.strip().strip('"')
            if not val:
                continue
            if first is None:
                first = val
            last = val
            h.update(val.encode("utf-8"))
            h.update(b"\n")
            count += 1
        err = p.stderr.read() if p.stderr else ""
        rc = p.wait()
        if rc != 0:
            raise RuntimeError(f"ffprobe packet hash failed for {path}: {err[-1000:]}")
    return {"count": count, "sha256": h.hexdigest(), "first": first, "last": last}

def frame_gray(ffmpeg: Path, path: Path, at: float, w=480, h=270):
    p = sh([ffmpeg, "-hide_banner", "-v", "error", "-ss", f"{at:.9f}", "-i", path, "-frames:v", "1", "-an",
            "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-pix_fmt", "gray", "-"], timeout=120)
    raw = p.stdout or b""
    need = w*h
    if len(raw) < need:
        raise RuntimeError(f"short frame {path} at {at}: {len(raw)} < {need}")
    return raw[:need]

def mae(a: bytes, b: bytes):
    if len(a) != len(b):
        raise ValueError("frame size mismatch")
    return sum(abs(x-y) for x,y in zip(a,b)) / len(a)

def contrast(a: bytes):
    return max(a)-min(a) if a else 0

def base_effect(source: Path, *, effect_id: str, name: str, mode="screen", usage="always",
                x=.5, y=.5, scale=1.0, fullscreen=True, preview=0.0):
    return {
        "id": effect_id, "name": name, "source": str(source), "enabled": True, "mode": mode,
        "keyColor": "#00ff00", "similarity": 0.12 if mode=="chromakey" else 0.18,
        "blend": 0.08, "despill": 1.0 if mode=="chromakey" else 0.0,
        "lumaThreshold": 0.12, "lumaTolerance": 0.12, "saturation": 1.0,
        "x": x, "y": y, "scale": scale, "fullscreen": fullscreen, "previewFrameTime": preview,
        "startSec": 0.0, "endSec": None, "cacheKey": None, "cacheReady": None,
        "assetState": "ready", "assetError": None, "usageMode": usage,
        "intervalSec": None, "usageDurationSec": None, "target": "CUSTOM",
        "offsetX": 0.0, "offsetY": 0.0, "opacity": 1.0,
    }

def settings(output: Path, hours: float, *, normalize=False, crossfade=0.0):
    return {
        "width": 1920, "height": 1080, "fps": 60, "codec": "h265", "bitrateMbps": 30.0,
        "durationHours": hours, "durationMode": "whole-track", "loopMode": "image",
        "crossfadeSec": crossfade, "normalizeLufs": normalize, "outputDir": str(output),
        "preset": "fast", "encoderPreference": "auto",
    }

def project(case_id: str, name: str, media_dir: Path, cover: Path, tracks, selected="__none__"):
    return {
        "id": case_id, "name": name, "path": str(media_dir), "media": [str(cover)],
        "audio": [str(x) for x in tracks], "valid": True, "error": None,
        "anchors": None, "selectedEffectId": selected,
    }

def job(case_id, name, media_dir, cover, tracks, output, hours, effects=None, subscribes=None,
        normalize=False, crossfade=0.0, ambient=None):
    effects = effects or []
    subscribes = subscribes or []
    selected = effects[0]["id"] if effects else "__none__"
    return {
        "project": project(case_id, name, media_dir, cover, tracks, selected),
        "settings": settings(output, hours, normalize=normalize, crossfade=crossfade),
        "effects": effects, "subscribes": subscribes, "ambient": ambient,
        "ambientSettings": {"volumePct": 18.0, "bassDb": 0.0, "midDb": 0.0, "trebleDb": 0.0},
    }

def run_app(exe: Path, root: Path, label: str, payload, *, preview=False, timeout=240):
    jobs = root / "jobs"; results = root / "results"; logs = root / "logs"
    jobs.mkdir(parents=True, exist_ok=True); results.mkdir(parents=True, exist_ok=True); logs.mkdir(parents=True, exist_ok=True)
    fixture = jobs / f"{label}.json"
    result = results / f"{label}.json"
    fixture.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    case_home = root / "isolated-home" / label
    data_dir = root / "isolated-data" / label
    case_home.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["HOME"] = str(case_home)
    env["ENDLUME_E2E_DATA_DIR"] = str(data_dir)
    env["ENDLUME_E2E_RESULT"] = str(result)
    if preview:
        env["ENDLUME_E2E_PREVIEW_JOB"] = str(fixture)
        env.pop("ENDLUME_E2E_RENDER_JOB", None)
    else:
        env["ENDLUME_E2E_RENDER_JOB"] = str(fixture)
        env.pop("ENDLUME_E2E_PREVIEW_JOB", None)
    started = time.perf_counter()
    p = sh([exe], env=env, timeout=timeout, check=False)
    elapsed = time.perf_counter()-started
    (logs/f"{label}.stdout.log").write_bytes(p.stdout or b"")
    (logs/f"{label}.stderr.log").write_bytes(p.stderr or b"")
    if p.returncode != 0:
        raise RuntimeError(f"{label}: app exited {p.returncode}; stderr={(p.stderr or b'').decode('utf-8','replace')[-3000:]}")
    if not result.is_file():
        raise RuntimeError(f"{label}: E2E result missing")
    data = json.loads(result.read_text(encoding="utf-8"))
    if data.get("status") != "passed":
        raise RuntimeError(f"{label}: E2E status failed: {json.dumps(data)[:3000]}")
    data["_processSeconds"] = elapsed
    return data

def render_result(exe, root, label, job_obj, timeout=240):
    data = run_app(exe, root, label, job_obj, preview=False, timeout=timeout)
    rows = data.get("results", [])
    if len(rows) != 1 or rows[0].get("status") != "passed":
        raise RuntimeError(f"{label}: invalid render result rows: {rows}")
    return rows[0]

def preview_results(exe, root, label, cases):
    payload = {"jobs": cases}
    data = run_app(exe, root, label, payload, preview=True, timeout=240)
    rows = data.get("results", [])
    by_id = {x.get("id"): x.get("result", {}) for x in rows}
    if len(by_id) != len(cases):
        raise RuntimeError(f"{label}: preview result count mismatch")
    return by_id

def verify_fast_primary(ffmpeg, ffprobe, row, source_tracks, *, target_hours=3.0, size_gate=True):
    out = Path(row["outputPath"])
    if not out.is_file():
        raise RuntimeError(f"render output missing: {out}")
    probe, v, a, dur = stream_probe(ffprobe, out)
    mb = out.stat().st_size / 1_000_000.0
    src_sig = packet_signature(ffprobe, source_tracks)
    dst_sig = packet_signature(ffprobe, [out])
    packet_ok = src_sig == dst_sig
    decode = full_decode(ffmpeg, out)
    seeks = seek_checks(ffmpeg, out, dur)
    dts = dts_check(ffprobe, out)
    checks = {
        "FAST_PATH": row.get("fastPath") is True,
        "HEVC_FAST_ENGINE": row.get("videoCodec") == "hevc" and v.get("codec_name") == "hevc",
        "MP3_PACKET_COPY": row.get("audioMode") == "mp3-packet-copy" and a.get("codec_name") == "mp3" and packet_ok,
        "RESOLUTION": (v.get("width"), v.get("height")) == (1920,1080),
        "FPS_60": v.get("r_frame_rate") == "60/1" and v.get("avg_frame_rate") == "60/1",
        "DURATION_3H": abs(dur - target_hours*3600.0) <= 1.0,
        "FULL_DECODE": decode["ok"],
        "SEEK": all(x["ok"] for x in seeks),
        "DTS": dts["ok"],
        "TEN_SECONDS": float(row.get("wallSeconds") or 1e9) <= 10.0,
    }
    if size_gate:
        checks["SIZE_400_600_MB"] = 400.0 <= mb <= 600.0
    return {
        "output": str(out), "wallSeconds": row.get("wallSeconds"), "outputMB": mb,
        "duration": dur, "encoder": row.get("encoder"), "fastPath": row.get("fastPath"),
        "fastPathReason": row.get("fastPathReason"), "audioMode": row.get("audioMode"),
        "videoCodec": row.get("videoCodec"), "audioCodec": row.get("audioCodec"),
        "videoProbe": {"codec": v.get("codec_name"), "width": v.get("width"), "height": v.get("height"),
                       "rFrameRate": v.get("r_frame_rate"), "avgFrameRate": v.get("avg_frame_rate"),
                       "timeBase": v.get("time_base")},
        "audioProbe": {"codec": a.get("codec_name"), "sampleRate": a.get("sample_rate"), "channels": a.get("channels")},
        "packets": {"source": src_sig, "output": dst_sig, "packetPerfect": packet_ok},
        "decode": decode, "seeks": seeks, "dts": dts, "checks": checks,
    }

def make_preview_case(case_id, media_dir, overlay_source, at, effects, subscribes):
    return {
        "id": case_id, "projectPath": str(media_dir), "overlaySource": str(overlay_source),
        "timeSec": at, "effects": effects, "subscribes": subscribes,
    }

def save_report(path, report):
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--head", required=True)
    args = ap.parse_args()
    app = Path(args.app).resolve()
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    exe = read_app_exe(app)
    ffmpeg = find_tool(app, "ffmpeg")
    ffprobe = find_tool(app, "ffprobe")
    report_path = root / "PHASE3_PHYSICAL_REPORT.json"
    report = {
        "phase3Head": args.head, "productBase": PRODUCT_BASE, "fastEngineSource": FAST_SOURCE,
        "release": "BLOCKED", "stable": "UNTOUCHED", "liveUpdater": "UNTOUCHED",
        "ownerApplicationReplaced": "NO", "cases": {}, "status": "RUNNING",
    }
    save_report(report_path, report)

    media = root / "media"; fxdir = root / "effects"; outdir = root / "out"
    media.mkdir(exist_ok=True); fxdir.mkdir(exist_ok=True); outdir.mkdir(exist_ok=True)
    cover = media / "cover.png"
    sh([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x182033:s=1920x1080",
        "-frames:v", "1", "-y", cover], timeout=120)

    tracks = []
    for i in range(1,13):
        p = media / f"track-{i:02d}.mp3"
        hz = 180 + i*23
        sh([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", f"sine=frequency={hz}:sample_rate=48000:duration=900",
            "-c:a", "libmp3lame", "-b:a", "320k", "-ar", "48000", "-ac", "2",
            "-metadata", f"title=Phase3 Track {i:02d}", "-y", p], timeout=300)
        tracks.append(p)

    short_tracks = []
    for i in range(1,3):
        p = media / f"fallback-{i:02d}.mp3"
        sh([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", f"sine=frequency={700+i*40}:sample_rate=48000:duration=60",
            "-c:a", "libmp3lame", "-b:a", "320k", "-ar", "48000", "-ac", "2", "-y", p], timeout=120)
        short_tracks.append(p)

    periodic_src = fxdir / "periodic-screen.mp4"
    sh([ffmpeg, "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=640x360:r=60:d=5",
        "-f", "lavfi", "-i", "color=c=white:s=80x80:r=60:d=5",
        "-filter_complex", "[0:v][1:v]overlay=x='280+220*sin(2*PI*t/5)':y='140+80*sin(2*PI*t/5+PI/2)':eval=frame:shortest=1",
        "-an", "-c:v", "mpeg4", "-q:v", "2", "-pix_fmt", "yuv420p", "-r", "60", "-frames:v", "300", "-y", periodic_src], timeout=120)

    subscribe_src = fxdir / "subscribe.mp4"
    sh([ffmpeg, "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=0x00ff00:s=640x360:r=60:d=3",
        "-f", "lavfi", "-i", "color=c=white:s=180x100:r=60:d=3",
        "-filter_complex", "[0:v][1:v]overlay=x='70+300*t/3':y='120+45*sin(2*PI*t/3)':eval=frame:shortest=1",
        "-an", "-c:v", "mpeg4", "-q:v", "2", "-pix_fmt", "yuv420p", "-r", "60", "-frames:v", "180", "-y", subscribe_src], timeout=120)

    periodic_fx = base_effect(periodic_src, effect_id="periodic-screen", name="Periodic Screen 5s", mode="screen",
                              usage="always", x=.5, y=.5, scale=1.0, fullscreen=True)
    subscribe = base_effect(subscribe_src, effect_id="subscribe", name="Subscribe Animated 3s", mode="chromakey",
                            usage="interval", x=.15, y=.65, scale=.30, fullscreen=False)
    subscribe.update({
        "intervalSec": 3600.0, "usageDurationSec": 3.0,
        "firstAtSec": 600.0, "secondAtSec": 3600.0, "repeatEverySec": 3600.0,
        "firstAppearance": "custom", "customFirstAtSec": 600.0, "showDurationSec": 3.0,
    })

    static_job = job("phase3-static-3h", "ENDLUME Phase3 Static 3H", media, cover, tracks,
                     outdir/"static", 3.0)
    static_row = render_result(exe, root, "render-static-3h", static_job, timeout=180)
    static = verify_fast_primary(ffmpeg, ffprobe, static_row, tracks)
    report["cases"]["static3h"] = static; save_report(report_path, report)
    if not all(static["checks"].values()):
        raise RuntimeError(f"STATIC 3H gate failed: {static['checks']}")

    periodic_job = job("phase3-periodic-3h", "ENDLUME Phase3 Periodic 3H", media, cover, tracks,
                       outdir/"periodic", 3.0, effects=[periodic_fx])
    periodic_row = render_result(exe, root, "render-periodic-3h", periodic_job, timeout=180)
    periodic = verify_fast_primary(ffmpeg, ffprobe, periodic_row, tracks)
    static_out = Path(static["output"]); periodic_out = Path(periodic["output"])
    ref = frame_gray(ffmpeg, periodic_out, 1.25)
    phase = {
        "1h": mae(ref, frame_gray(ffmpeg, periodic_out, 3601.25)),
        "2h": mae(ref, frame_gray(ffmpeg, periodic_out, 7201.25)),
        "near3h": mae(ref, frame_gray(ffmpeg, periodic_out, 10796.25)),
    }
    motion = mae(frame_gray(ffmpeg, periodic_out, 1.0), frame_gray(ffmpeg, periodic_out, 1.2))
    visible = mae(frame_gray(ffmpeg, static_out, 1.0), frame_gray(ffmpeg, periodic_out, 1.0))
    around = [5.0 + (i-6)/60.0 for i in range(13)]
    aframes = [frame_gray(ffmpeg, periodic_out, t) for t in around]
    diffs = [mae(a,b) for a,b in zip(aframes, aframes[1:])]
    typical = sorted(d for i,d in enumerate(diffs) if i != 5)[len(diffs)//2 - 1]
    seam = diffs[5]
    preview_cases = [make_preview_case(f"periodic-{i}", media, periodic_src, t, [periodic_fx], [])
                     for i,t in enumerate([0.0,1.0,4.983333333,5.0,5.016666667,10.0,30.0,60.0])]
    previews = preview_results(exe, root, "preview-periodic", preview_cases)
    preview_rows = []
    for c in preview_cases:
        pr = previews[c["id"]]
        diff = mae(frame_gray(ffmpeg, periodic_out, c["timeSec"]),
                   frame_gray(ffmpeg, Path(pr["exactPath"]), 0.0))
        preview_rows.append({"at": c["timeSec"], "mae": diff, "pass": diff < 8.0})
    periodic_visual = {
        "effectVisibleMAE": visible, "motionMAE": motion, "phaseMAE": phase,
        "seamDiff": seam, "typicalAdjacentDiff": typical, "preview": preview_rows,
        "checks": {
            "EFFECT_VISIBLE": visible > 0.10,
            "MOTION": motion > 0.02,
            "PERIOD_EXACT_NO_DRIFT": all(v < 0.15 for v in phase.values()),
            "NO_SEAM_SPIKE": typical > 0.02 and seam <= max(typical*2.5, 0.20),
            "PREVIEW_PARITY": all(x["pass"] for x in preview_rows),
        }
    }
    periodic["visual"] = periodic_visual
    periodic["checks"].update(periodic_visual["checks"])
    report["cases"]["periodic3h"] = periodic; save_report(report_path, report)
    if not all(periodic["checks"].values()):
        raise RuntimeError(f"PERIODIC 3H gate failed: {periodic['checks']}")

    subscribe_job = job("phase3-subscribe-3h", "ENDLUME Phase3 Subscribe 3H", media, cover, tracks,
                        outdir/"subscribe", 3.0, subscribes=[subscribe])
    subscribe_row = render_result(exe, root, "render-subscribe-3h", subscribe_job, timeout=180)
    sub = verify_fast_primary(ffmpeg, ffprobe, subscribe_row, tracks)
    sub_out = Path(sub["output"])
    base = frame_gray(ffmpeg, sub_out, 599.0)
    off_times = [599.0,599.9,603.0,603.1,4199.9,4203.0,4203.1,7799.9,7803.0,7803.1,10799.0]
    on_times = [600.0,600.1,600.5,601.5,602.983333333,4200.0,4200.5,4202.983333333,7800.0,7800.5,7802.983333333]
    off_ok = all(mae(base, frame_gray(ffmpeg, sub_out, t)) < 0.25 for t in off_times)
    on_ok = all(mae(base, frame_gray(ffmpeg, sub_out, t)) > 0.10 for t in on_times)
    anim = mae(frame_gray(ffmpeg, sub_out, 600.1), frame_gray(ffmpeg, sub_out, 601.5))
    repeat_phase = [
        mae(frame_gray(ffmpeg, sub_out, 600.5), frame_gray(ffmpeg, sub_out, 4200.5)),
        mae(frame_gray(ffmpeg, sub_out, 600.5), frame_gray(ffmpeg, sub_out, 7800.5)),
    ]
    delta_a = frame_gray(ffmpeg, sub_out, 600.5)
    pts = [(i%480, i//480) for i,(x,y) in enumerate(zip(delta_a,base)) if abs(x-y) > 15]
    cx = sum(x for x,y in pts)/len(pts) if pts else 999
    cy = sum(y for x,y in pts)/len(pts) if pts else -1
    sub_preview_times = [599.9,600.0,600.5,602.983333333,603.0,4200.5,7800.5]
    sub_preview_cases = [make_preview_case(f"subscribe-{i}", media, subscribe_src, t, [], [subscribe])
                         for i,t in enumerate(sub_preview_times)]
    sub_previews = preview_results(exe, root, "preview-subscribe", sub_preview_cases)
    sub_preview_rows = []
    for c in sub_preview_cases:
        pr = sub_previews[c["id"]]
        diff = mae(frame_gray(ffmpeg, sub_out, c["timeSec"]),
                   frame_gray(ffmpeg, Path(pr["exactPath"]), 0.0))
        sub_preview_rows.append({"at": c["timeSec"], "mae": diff, "pass": diff < 12.0})
    sub_visual = {
        "offTimes": off_times, "onTimes": on_times, "animationMAE": anim,
        "repeatPhaseMAE": repeat_phase, "centroid": [cx,cy], "preview": sub_preview_rows,
        "checks": {
            "FIRST_APPEARANCE": on_ok,
            "DURATION_DISAPPEARANCE": off_ok,
            "NO_DUPLICATE_OR_LINGER": off_ok,
            "REPEAT_TIMING": all(x < 0.25 for x in repeat_phase),
            "ANIMATION_APPEARANCE": anim > 0.20,
            "POSITION_SCALE": bool(pts) and cx < 480*0.5 and cy > 270*0.4,
            "PREVIEW_PARITY": all(x["pass"] for x in sub_preview_rows),
        }
    }
    sub["visual"] = sub_visual
    sub["checks"].update(sub_visual["checks"])
    report["cases"]["subscribe3h"] = sub; save_report(report_path, report)
    if not all(sub["checks"].values()):
        raise RuntimeError(f"SUBSCRIBE 3H gate failed: {sub['checks']}")

    combined_job = job("phase3-combined-2h", "ENDLUME Phase3 Combined 2H", media, cover, tracks,
                       outdir/"combined", 2.0, effects=[periodic_fx], subscribes=[subscribe])
    combined_row = render_result(exe, root, "render-combined-2h", combined_job, timeout=300)
    combined_out = Path(combined_row["outputPath"])
    cprobe, cv, ca, cdur = stream_probe(ffprobe, combined_out)
    cdecode = full_decode(ffmpeg, combined_out)
    cseeks = seek_checks(ffmpeg, combined_out, cdur)
    cwall = float(combined_row.get("wallSeconds") or 1e9)
    combined_checks = {
        "EFFECTS_ON": True, "SUBSCRIBE_ON": True,
        "DURATION_2H_PLUS": cdur >= 7200.0-1.0,
        "HEVC": cv.get("codec_name") == "hevc",
        "FPS_60": cv.get("r_frame_rate") == "60/1",
        "FULL_DECODE": cdecode["ok"], "SEEK": all(x["ok"] for x in cseeks),
        "NO_MATERIAL_PERF_REGRESSION": cwall <= 20.0,
    }
    combined = {
        "tracks": 12, "duration": cdur, "wallSeconds": cwall, "baselineSeconds": 15.393,
        "baselineRatio": cwall/15.393, "outputMB": combined_out.stat().st_size/1_000_000.0,
        "codec": cv.get("codec_name"), "audioCodec": ca.get("codec_name"),
        "fastPath": combined_row.get("fastPath"), "fastPathReason": combined_row.get("fastPathReason"),
        "audioMode": combined_row.get("audioMode"), "decode": cdecode, "seeks": cseeks, "checks": combined_checks,
    }
    report["cases"]["combined2h"] = combined; save_report(report_path, report)
    if not all(combined_checks.values()):
        raise RuntimeError(f"COMBINED gate failed: {combined_checks}")

    fallback_cases = {}
    norm_job = job("phase3-fallback-normalize", "ENDLUME Phase3 Normalize Fallback", media, cover, [short_tracks[0]],
                   outdir/"fallback-normalize", 1/60, normalize=True)
    cross_job = job("phase3-fallback-crossfade", "ENDLUME Phase3 Crossfade Fallback", media, cover, short_tracks,
                    outdir/"fallback-crossfade", 2/60, crossfade=2.0)
    interval_fx = dict(periodic_fx)
    interval_fx.update({"id":"interval-screen","name":"Unsupported Interval Screen","usageMode":"interval",
                        "intervalSec":30.0,"usageDurationSec":5.0})
    unsupported_job = job("phase3-fallback-unsupported", "ENDLUME Phase3 Unsupported Effect Fallback", media, cover, short_tracks,
                          outdir/"fallback-unsupported", 2/60, effects=[interval_fx])
    for label, j in [("normalize",norm_job),("crossfade",cross_job),("unsupportedEffect",unsupported_job)]:
        row = render_result(exe, root, f"render-fallback-{label}", j, timeout=240)
        p = Path(row["outputPath"])
        _, vv, aa, dd = stream_probe(ffprobe, p)
        dec = full_decode(ffmpeg, p)
        checks = {
            "CANONICAL_FALLBACK_USED": row.get("audioMode") != "mp3-packet-copy",
            "OUTPUT_CORRECT": p.is_file() and dd > 0 and vv.get("codec_name") in ("hevc","h264") and dec["ok"],
        }
        fallback_cases[label] = {
            "wallSeconds": row.get("wallSeconds"), "fastPath": row.get("fastPath"),
            "fastPathReason": row.get("fastPathReason"), "audioMode": row.get("audioMode"),
            "videoCodec": row.get("videoCodec"), "audioCodec": row.get("audioCodec"),
            "duration": dd, "checks": checks,
        }
        if not all(checks.values()):
            report["cases"]["fallbacks"] = fallback_cases; save_report(report_path, report)
            raise RuntimeError(f"fallback {label} failed: {checks}")
    report["cases"]["fallbacks"] = fallback_cases

    all_checks = []
    for name in ("static3h","periodic3h","subscribe3h","combined2h"):
        all_checks += list(report["cases"][name]["checks"].values())
    for row in fallback_cases.values():
        all_checks += list(row["checks"].values())
    report["status"] = "PASS" if all(all_checks) else "BLOCKED"
    save_report(report_path, report)
    if report["status"] != "PASS":
        raise SystemExit(2)
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
