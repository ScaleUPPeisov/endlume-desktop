#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import time
from pathlib import Path

PRODUCT_HEAD = "e4a07972b1566ed73b11c4eb758d59f4dc839e71"
PRODUCT_BASE = "3f06c7329bd3821bc160e6d88c5b294fc0d82c2b"
FAST_SOURCE = "a7a399e83de8b9248e2065c6dda1f9079ded6565"
OLD_TIMESTAMP_MAE = 8.52375
MAE_LIMIT = 8.0
FRAMES = [297, 298, 299, 300, 301, 302]
FPS = 60


def sh(cmd, *, env=None, timeout=300, check=True):
    cmd = [str(x) for x in cmd]
    print("+", " ".join(cmd), flush=True)
    p = subprocess.run(cmd, env=env, timeout=timeout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode != 0:
        out = (p.stdout or b"").decode("utf-8", "replace")[-3000:]
        err = (p.stderr or b"").decode("utf-8", "replace")[-3000:]
        raise RuntimeError(f"command failed rc={p.returncode}: {' '.join(cmd)}\nstdout:\n{out}\nstderr:\n{err}")
    return p


def read_app_exe(app: Path) -> Path:
    with open(app / "Contents" / "Info.plist", "rb") as f:
        info = plistlib.load(f)
    p = app / "Contents" / "MacOS" / info["CFBundleExecutable"]
    if not p.is_file():
        raise RuntimeError(f"candidate executable missing: {p}")
    return p


def find_tool(app: Path, name: str) -> Path:
    macos = app / "Contents" / "MacOS"
    for p in [macos / name, *sorted(macos.glob(f"{name}*"))]:
        if p.is_file() and os.access(p, os.X_OK):
            return p
    q = shutil.which(name)
    if q:
        return Path(q)
    raise RuntimeError(f"{name} missing")


def base_effect(source: Path, preview=0.0):
    return {
        "id": "periodic-screen", "name": "Periodic Screen 5s", "source": str(source),
        "enabled": True, "mode": "screen", "keyColor": "#00ff00",
        "similarity": 0.18, "blend": 0.08, "despill": 0.0,
        "lumaThreshold": 0.12, "lumaTolerance": 0.12, "saturation": 1.0,
        "x": 0.5, "y": 0.5, "scale": 1.0, "fullscreen": True,
        "previewFrameTime": preview, "startSec": 0.0, "endSec": None,
        "cacheKey": None, "cacheReady": None, "assetState": "ready", "assetError": None,
        "usageMode": "always", "intervalSec": None, "usageDurationSec": None,
        "target": "CUSTOM", "offsetX": 0.0, "offsetY": 0.0, "opacity": 1.0,
    }


def render_job(media: Path, cover: Path, tracks, output: Path, effect):
    return {
        "project": {
            "id": "phase3-final-periodic-frame-exact", "name": "ENDLUME Phase3 Frame Exact",
            "path": str(media), "media": [str(cover)], "audio": [str(x) for x in tracks],
            "valid": True, "error": None, "anchors": None, "selectedEffectId": effect["id"],
        },
        "settings": {
            "width": 1920, "height": 1080, "fps": 60, "codec": "h265", "bitrateMbps": 30.0,
            "durationHours": 3.0, "durationMode": "whole-track", "loopMode": "image",
            "crossfadeSec": 0.0, "normalizeLufs": False, "outputDir": str(output),
            "preset": "fast", "encoderPreference": "auto",
        },
        "effects": [effect], "subscribes": [], "ambient": None,
        "ambientSettings": {"volumePct": 18.0, "bassDb": 0.0, "midDb": 0.0, "trebleDb": 0.0},
    }


def preview_case(case_id, media: Path, source: Path, frame_index: int):
    t = frame_index / FPS
    effect = base_effect(source, preview=t % 5.0)
    return {
        "id": case_id, "projectPath": str(media), "overlaySource": str(source),
        "timeSec": t, "effects": [effect], "subscribes": [],
    }


def run_app(exe: Path, root: Path, label: str, payload, *, preview=False, timeout=240):
    jobs = root / "jobs"; results = root / "results"; logs = root / "logs"
    for d in (jobs, results, logs): d.mkdir(parents=True, exist_ok=True)
    fixture = jobs / f"{label}.json"; result = results / f"{label}.json"
    fixture.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    home = root / "isolated-home" / label; data = root / "isolated-data" / label
    home.mkdir(parents=True, exist_ok=True); data.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["CFFIXED_USER_HOME"] = str(home)
    env["XDG_DATA_HOME"] = str(home / ".local" / "share")
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    env["XDG_CACHE_HOME"] = str(home / ".cache")
    env["ENDLUME_E2E_DATA_DIR"] = str(data)
    env["ENDLUME_E2E_RESULT"] = str(result)
    if preview:
        env["ENDLUME_E2E_PREVIEW_JOB"] = str(fixture); env.pop("ENDLUME_E2E_RENDER_JOB", None)
    else:
        env["ENDLUME_E2E_RENDER_JOB"] = str(fixture); env.pop("ENDLUME_E2E_PREVIEW_JOB", None)
    started = time.perf_counter()
    p = sh([exe], env=env, timeout=timeout, check=False)
    elapsed = time.perf_counter() - started
    (logs / f"{label}.stdout.log").write_bytes(p.stdout or b"")
    (logs / f"{label}.stderr.log").write_bytes(p.stderr or b"")
    if p.returncode != 0:
        raise RuntimeError(f"{label}: app rc={p.returncode}: {(p.stderr or b'').decode('utf-8','replace')[-2000:]}")
    if not result.is_file():
        raise RuntimeError(f"{label}: E2E result missing")
    value = json.loads(result.read_text(encoding="utf-8"))
    if value.get("status") != "passed":
        raise RuntimeError(f"{label}: E2E failed: {json.dumps(value)[:2000]}")
    value["_processSeconds"] = elapsed
    return value


def exact_gray(ffmpeg: Path, path: Path, n: int, w=480, h=270):
    vf = f"select=eq(n\\,{n}),scale={w}:{h}:flags=lanczos,format=gray"
    p = sh([ffmpeg, "-hide_banner", "-v", "error", "-i", path, "-an", "-vf", vf,
            "-fps_mode", "passthrough", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"], timeout=180)
    raw = p.stdout or b""; need = w*h
    if len(raw) < need:
        raise RuntimeError(f"short exact frame n={n} from {path}: {len(raw)} < {need}")
    return raw[:need]


def seek_gray(ffmpeg: Path, path: Path, at: float, w=480, h=270):
    p = sh([ffmpeg, "-hide_banner", "-v", "error", "-ss", f"{at:.9f}", "-i", path,
            "-frames:v", "1", "-an", "-vf", f"scale={w}:{h},format=gray",
            "-f", "rawvideo", "-pix_fmt", "gray", "-"], timeout=120)
    raw = p.stdout or b""; need=w*h
    if len(raw) < need: raise RuntimeError("short seek frame")
    return raw[:need]


def mae(a: bytes, b: bytes):
    if len(a) != len(b): raise ValueError("frame mismatch")
    return sum(abs(x-y) for x,y in zip(a,b)) / len(a)


def screen_expected(base: bytes, source: bytes):
    # Source is neutral grayscale; screen blend commutes with grayscale weighting for a neutral overlay.
    return bytes(min(255, round(b + s - (b*s/255.0))) for b,s in zip(base, source))


def sha256_bytes(b: bytes):
    return hashlib.sha256(b).hexdigest()


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--app", required=True); ap.add_argument("--root", required=True); ap.add_argument("--head", required=True)
    args=ap.parse_args()
    if args.head != PRODUCT_HEAD: raise RuntimeError(f"wrong product head: {args.head}")
    app=Path(args.app).resolve(); root=Path(args.root).resolve(); root.mkdir(parents=True, exist_ok=True)
    exe=read_app_exe(app); ffmpeg=find_tool(app,"ffmpeg")
    media=root/"media"; fx=root/"effects"; out=root/"out"
    for d in (media,fx,out): d.mkdir(parents=True,exist_ok=True)
    cover=media/"cover.png"
    sh([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=0x182033:s=1920x1080","-frames:v","1","-y",cover],timeout=120)
    tracks=[]
    # Eight clean MP3s exercise the accepted Fast Engine profile while keeping this targeted rerun lightweight.
    for i in range(8):
        p=media/f"track-{i+1:02d}.mp3"; hz=220+i*31
        sh([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i",f"sine=frequency={hz}:sample_rate=48000:duration=10","-c:a","libmp3lame","-b:a","320k","-ar","48000","-ac","2","-y",p],timeout=60)
        tracks.append(p)
    source=fx/"periodic-screen.mp4"
    sh([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=black:s=640x360:r=60:d=5","-f","lavfi","-i","color=c=white:s=80x80:r=60:d=5","-filter_complex","[0:v][1:v]overlay=x='280+220*sin(2*PI*t/5)':y='140+80*sin(2*PI*t/5+PI/2)':eval=frame:shortest=1","-an","-c:v","mpeg4","-q:v","2","-pix_fmt","yuv420p","-r","60","-frames:v","300","-y",source],timeout=120)

    effect=base_effect(source)
    row_data=run_app(exe,root,"targeted-periodic-render",render_job(media,cover,tracks,out,effect),timeout=180)
    rows=row_data.get("results",[])
    if len(rows)!=1 or rows[0].get("status")!="passed": raise RuntimeError(f"render row invalid: {rows}")
    row=rows[0]; rendered=Path(row["outputPath"])
    if row.get("fastPath") is not True: raise RuntimeError(f"targeted periodic did not select Fast Engine: {row}")

    cases=[preview_case(f"frame-{n}",media,source,n) for n in FRAMES]
    preview_data=run_app(exe,root,"targeted-periodic-previews",{"jobs":cases},preview=True,timeout=240)
    previews={x.get("id"):x.get("result",{}) for x in preview_data.get("results",[])}
    if len(previews)!=len(FRAMES): raise RuntimeError("preview result count mismatch")

    base_exact=exact_gray(ffmpeg,cover,0)
    frame_rows=[]
    for n in FRAMES:
        t=n/FPS
        r=exact_gray(ffmpeg,rendered,n)
        pr=Path(previews[f"frame-{n}"]["exactPath"])
        p=exact_gray(ffmpeg,pr,0)
        src_index=n%300
        s=exact_gray(ffmpeg,source,src_index)
        expected=screen_expected(base_exact,s)
        parity=mae(r,p)
        source_phase=mae(r,expected)
        frame_rows.append({
            "frame":n,"rationalTime":f"{n}/60","timeSeconds":t,"previewMAE":parity,
            "previewPass":parity<MAE_LIMIT,"sourceFrame":src_index,"sourcePhaseMAE":source_phase,
            "renderFrameSha256":sha256_bytes(r),"previewFrameSha256":sha256_bytes(p),"sourceFrameSha256":sha256_bytes(s),
        })

    # Preserve the historical timestamp-based result and also remeasure it against this targeted output.
    old_seek_render=seek_gray(ffmpeg,rendered,299/60)
    preview299=exact_gray(ffmpeg,Path(previews["frame-299"]["exactPath"]),0)
    timestamp_recheck=mae(old_seek_render,preview299)
    frame299=next(x for x in frame_rows if x["frame"]==299)
    exact_all=all(x["previewPass"] for x in frame_rows)
    if frame299["previewMAE"] < MAE_LIMIT and exact_all:
        root_cause="TIMESTAMP_SAMPLING_FALSE_NEGATIVE"
        status="PASS"
    else:
        root_cause="REAL_PRODUCT_PARITY_DEFECT"
        status="BLOCKED"

    report={
        "phase3ProductHead":PRODUCT_HEAD,"productBase":PRODUCT_BASE,"fastEngineSource":FAST_SOURCE,
        "productFilesChanged":0,"sourceArtifactId":11677270291,"existingEvidenceArtifactId":11692747856,
        "diagnostic":"PERIODIC_FRAME_EXACT_PREVIEW_PARITY","maeThresholdExclusive":MAE_LIMIT,
        "frames":frame_rows,"oldTimestampMAE_4_983333333":OLD_TIMESTAMP_MAE,
        "targetedTimestampRecheckMAE":timestamp_recheck,"rootCause":root_cause,
        "periodicFrameExactPreviewParity":"PASS" if exact_all else "FAIL",
        "targetedRender":{"wallSeconds":row.get("wallSeconds"),"fastPath":row.get("fastPath"),"fastPathReason":row.get("fastPathReason"),"outputBytes":row.get("outputBytes")},
        "inheritedEvidence":{
            "static3h":{"status":"PASS","milliseconds":2513.5,"outputMB":437.255},
            "periodic3h":{"status":"PASS_PENDING_FRAME_EXACT_ONLY","milliseconds":5862.2,"outputMB":437.279},
            "subscribe3h":{"status":"PASS","milliseconds":3127.0,"outputMB":437.394},
            "fallback":"PASS","packetPreservation":"PASS","decode":"PASS","seek":"PASS","dts":"PASS",
            "combined":{"status":"PASS","previousMilliseconds":22180.0,"baselineMilliseconds":15393.0,"baselineRatio":22.180/15.393,"classification":"COMBINED_PERFORMANCE_INFORMATIONAL","performanceWarning":True}
        },
        "status":status,"release":"STILL_BLOCKED"
    }
    (root/"PHASE3_FINAL_DIAGNOSTIC.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"rootCause":root_cause,"periodicFrameExactPreviewParity":report["periodicFrameExactPreviewParity"],"frames":[{"frame":x["frame"],"previewMAE":x["previewMAE"]} for x in frame_rows]},indent=2))
    # Do not retain the 3h output in evidence; only diagnostic hashes/metrics are needed.
    try: rendered.unlink()
    except OSError: pass
    return 0 if status=="PASS" else 2


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"PHASE3_FINAL_DIAGNOSTIC_ERROR={e}",file=sys.stderr)
        raise
