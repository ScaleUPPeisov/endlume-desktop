#!/usr/bin/env python3
# ENDLUME 8.57 durable real-fixture locator; CI trigger 2026-09-05.
import copy
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

UUID = "2e0e14ba-d97a-48d5-ab32-2fb2b27754bf"
HOME = Path.home()
STAGE = HOME / ".endlume-ci-fixtures" / UUID
ENV_FILE = Path(sys.argv[1]) if len(sys.argv) > 1 else None


def log(msg: str) -> None:
    print(f"[fixture] {msg}", flush=True)


def maybe_mount_known_volume() -> None:
    mount = Path("/Volumes/TOSHIBA EXT")
    if mount.is_dir():
        log(f"known volume already mounted: {mount}")
        return
    try:
        out = subprocess.run(["/usr/sbin/diskutil", "list"], capture_output=True, text=True, timeout=15, check=False)
    except Exception as exc:
        log(f"diskutil list unavailable: {exc}")
        return
    for line in out.stdout.splitlines():
        if "TOSHIBA EXT" not in line:
            continue
        ident = line.split()[-1] if line.split() else ""
        if not re.fullmatch(r"disk\d+s\d+", ident):
            continue
        log(f"known volume present but unmounted; trying diskutil mount {ident}")
        try:
            res = subprocess.run(["/usr/sbin/diskutil", "mount", ident], capture_output=True, text=True, timeout=30, check=False)
            log((res.stdout or res.stderr).strip() or f"diskutil mount exit={res.returncode}")
        except Exception as exc:
            log(f"mount attempt failed: {exc}")
        break


def resolve_path(raw, side: Path) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    p = Path(os.path.expanduser(raw))
    if p.is_file():
        return p.resolve()
    if not p.is_absolute():
        for base in [side.parent, *list(side.parents)[:6]]:
            q = (base / p)
            if q.is_file():
                return q.resolve()
    return None


def validate_data(data, side: Path):
    if not isinstance(data, dict):
        return None, "root is not object"
    project = data.get("project")
    effects = data.get("effects")
    if not isinstance(project, dict) or not isinstance(effects, list):
        return None, "missing project/effects"
    media = project.get("media") or []
    audio = project.get("audio") or []
    enabled = [x for x in effects if isinstance(x, dict) and x.get("enabled")]
    if len(media) != 1:
        return None, f"media={len(media)} not 1"
    if len(audio) != 15:
        return None, f"audio={len(audio)} not 15"
    if len(enabled) < 2:
        return None, f"enabled_effects={len(enabled)} < 2"
    image = resolve_path(media[0], side)
    audios = [resolve_path(x, side) for x in audio]
    fx = [resolve_path(x.get("source"), side) for x in enabled]
    missing = []
    if image is None:
        missing.append(f"image:{media[0]}")
    missing.extend(f"audio[{i}]:{audio[i]}" for i, p in enumerate(audios) if p is None)
    missing.extend(f"effect[{i}]:{enabled[i].get('source')}" for i, p in enumerate(fx) if p is None)
    if missing:
        return None, "missing assets: " + "; ".join(missing[:8]) + (" ..." if len(missing) > 8 else "")
    return {
        "data": data,
        "side": side,
        "image": image,
        "audios": audios,
        "enabled_effects": enabled,
        "effect_paths": fx,
    }, "ok"


def validate_side(side: Path):
    try:
        data = json.loads(side.read_text(errors="replace"))
    except Exception as exc:
        return None, f"json error: {exc}"
    return validate_data(data, side)


def find_with_find(root: Path, timeout: int = 20):
    if not root.exists():
        return []
    cmd = ["/usr/bin/find", str(root), "-type", "f", "-path", "*/Rendered/logs/*", "-name", "*project.json", "-print"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        log(f"find timeout under {root}")
        return []
    return [Path(x) for x in res.stdout.splitlines() if x.strip()]


def state_candidates():
    app_support = HOME / "Library" / "Application Support"
    if not app_support.is_dir():
        return []
    found = []
    try:
        res = subprocess.run(
            ["/usr/bin/find", str(app_support), "-maxdepth", "6", "-type", "f", "(", "-name", "queue.json", "-o", "-name", "recovery.json", "-o", "-name", "session.json", ")", "-print"],
            capture_output=True, text=True, timeout=15, check=False,
        )
        found = [Path(x) for x in res.stdout.splitlines() if x.strip()]
    except Exception as exc:
        log(f"state search failed: {exc}")
    return found


def walk_side_like(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get("project"), dict) and isinstance(obj.get("effects"), list):
            yield obj
        for value in obj.values():
            yield from walk_side_like(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from walk_side_like(value)


def write_state_candidate(state_file: Path, obj: dict) -> Path:
    temp_dir = STAGE / "recovered-state"
    temp_dir.mkdir(parents=True, exist_ok=True)
    out = temp_dir / (state_file.stem + "-project.json")
    out.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
    return out


def stage_fixture(info):
    STAGE.mkdir(parents=True, exist_ok=True)
    media_dir = STAGE / "media"
    audio_dir = STAGE / "audio"
    fx_dir = STAGE / "effects"
    for d in (media_dir, audio_dir, fx_dir):
        d.mkdir(parents=True, exist_ok=True)

    def cp(src: Path, dst: Path):
        if not dst.exists() or dst.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dst)
        return dst.resolve()

    staged = copy.deepcopy(info["data"])
    img_src = info["image"]
    img_dst = cp(img_src, media_dir / ("image" + img_src.suffix.lower()))
    staged["project"]["media"] = [str(img_dst)]

    audio_dst = []
    for i, src in enumerate(info["audios"], 1):
        dst = cp(src, audio_dir / f"{i:02d}{src.suffix.lower()}")
        audio_dst.append(str(dst))
    staged["project"]["audio"] = audio_dst

    enabled_idx = 0
    for effect in staged["effects"]:
        if not isinstance(effect, dict) or not effect.get("enabled"):
            continue
        src = info["effect_paths"][enabled_idx]
        enabled_idx += 1
        dst = cp(src, fx_dir / f"fx{enabled_idx:02d}{src.suffix.lower()}")
        effect["source"] = str(dst)

    side = STAGE / "project.json"
    side.write_text(json.dumps(staged, ensure_ascii=False, indent=2))
    staged_info, reason = validate_side(side)
    if not staged_info:
        raise RuntimeError(f"staged fixture invalid: {reason}")
    log(f"staged durable real fixture: {side}")
    return staged_info


def emit(info):
    side = info["side"]
    image = info["image"]
    fx = info["effect_paths"]
    project = info["data"].get("project", {})
    values = {
        "SIDE": str(side),
        "IMG": str(image),
        "FX1": str(fx[0]),
        "FX2": str(fx[1]),
        "AUDIO_COUNT": str(len(info["audios"])),
        "PROJECT_NAME": str(project.get("name") or ""),
        "PROJECT_ID": str(project.get("id") or UUID),
    }
    log(f"selected real fixture side={side}")
    log(f"project={values['PROJECT_NAME']!r} media=1 audio=15 effects>={len(fx)}")
    if ENV_FILE:
        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        ENV_FILE.write_text("\n".join(f"{k}={shlex.quote(v)}" for k, v in values.items()) + "\n")
    else:
        print(json.dumps(values, ensure_ascii=False, indent=2))


maybe_mount_known_volume()

# 1) Prefer the durable staged copy from a previous successful discovery.
staged_side = STAGE / "project.json"
if staged_side.is_file():
    info, reason = validate_side(staged_side)
    if info:
        log("using previously staged durable real fixture")
        emit(info)
        raise SystemExit(0)
    log(f"staged fixture rejected: {reason}")

# 2) Exact known real batch and any explicitly supplied side file.
candidates = []
explicit = os.environ.get("ENDLUME_E2E_SIDE")
if explicit:
    candidates.append(Path(os.path.expanduser(explicit)))
known_batch = Path("/Volumes/TOSHIBA EXT/ВАЙРОН/ProductionManager/Batches") / UUID
if known_batch.is_dir():
    candidates.extend(known_batch.glob("**/Rendered/logs/*project.json"))

# 3) Search common local/macOS locations, then HOME as a bounded fallback.
roots = [
    Path("/Volumes"),
    HOME / "Desktop",
    HOME / "Documents",
    HOME / "Downloads",
    HOME / "Movies",
    HOME / "Library" / "Application Support",
    HOME / ".endlume-local-builder",
    Path("/Users/Shared"),
]
seen = set()
for root in roots:
    for p in find_with_find(root, 20):
        s = str(p)
        if s not in seen:
            seen.add(s)
            candidates.append(p)
if not candidates:
    for p in find_with_find(HOME, 30):
        s = str(p)
        if s not in seen:
            seen.add(s)
            candidates.append(p)

for side in candidates:
    if not side.is_file():
        continue
    info, reason = validate_side(side)
    if not info:
        if UUID in str(side):
            log(f"exact-UUID side rejected {side}: {reason}")
        continue
    try:
        info = stage_fixture(info)
    except Exception as exc:
        log(f"staging failed; using original real fixture: {exc}")
    emit(info)
    raise SystemExit(0)

# 4) Recover a compatible real project snapshot from ENDLUME persisted state.
for state in state_candidates():
    try:
        raw = json.loads(state.read_text(errors="replace"))
    except Exception:
        continue
    for obj in walk_side_like(raw):
        temp = write_state_candidate(state, obj)
        info, reason = validate_side(temp)
        if not info:
            continue
        try:
            info = stage_fixture(info)
        except Exception as exc:
            log(f"state fixture staging failed: {exc}")
        emit(info)
        raise SystemExit(0)

log("NO VALID REAL 1-image + 15-audio + >=2-effects fixture found")
log("Volumes now: " + ", ".join(p.name for p in Path('/Volumes').iterdir()) if Path('/Volumes').is_dir() else "Volumes directory unavailable")
log("Connect/mount the real project drive once; the next successful run will stage a durable local CI copy under ~/.endlume-ci-fixtures")
raise SystemExit(2)
