#!/usr/bin/env python3
# ENDLUME 8.57 durable real-fixture locator.
# Keeps one verified physical 1-image + 15-audio + >=2-effects project locally
# so strict render gates no longer depend on the external disk after discovery.
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
KNOWN_VOLUME = Path("/Volumes/TOSHIBA EXT")
KNOWN_BATCH = KNOWN_VOLUME / "ВАЙРОН" / "ProductionManager" / "Batches" / UUID


def log(msg: str) -> None:
    print(f"[fixture] {msg}", flush=True)


def maybe_mount_known_volume() -> None:
    if KNOWN_VOLUME.is_dir():
        log(f"known volume already mounted: {KNOWN_VOLUME}")
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
            q = base / p
            if q.is_file():
                return q.resolve()
    return None


def active_subscribes(data):
    subs = data.get("subscribes") or []
    if not isinstance(subs, list):
        return []
    return [
        x for x in subs
        if isinstance(x, dict) and x.get("enabled") and isinstance(x.get("source"), str) and x.get("source", "").strip()
    ]


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
    subs = active_subscribes(data)
    if len(media) != 1:
        return None, f"media={len(media)} not 1"
    if len(audio) != 15:
        return None, f"audio={len(audio)} not 15"
    if len(enabled) < 2:
        return None, f"enabled_effects={len(enabled)} < 2"

    image = resolve_path(media[0], side)
    audios = [resolve_path(x, side) for x in audio]
    fx = [resolve_path(x.get("source"), side) for x in enabled]
    sub_paths = [resolve_path(x.get("source"), side) for x in subs]
    missing = []
    if image is None:
        missing.append(f"image:{media[0]}")
    missing.extend(f"audio[{i}]:{audio[i]}" for i, p in enumerate(audios) if p is None)
    missing.extend(f"effect[{i}]:{enabled[i].get('source')}" for i, p in enumerate(fx) if p is None)
    missing.extend(f"subscribe[{i}]:{subs[i].get('source')}" for i, p in enumerate(sub_paths) if p is None)
    if missing:
        return None, "missing assets: " + "; ".join(missing[:10]) + (" ..." if len(missing) > 10 else "")

    return {
        "data": data,
        "side": side,
        "image": image,
        "audios": audios,
        "enabled_effects": enabled,
        "effect_paths": fx,
        "active_subscribes": subs,
        "subscribe_paths": sub_paths,
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
    try:
        res = subprocess.run(
            ["/usr/bin/find", str(app_support), "-maxdepth", "6", "-type", "f", "(", "-name", "queue.json", "-o", "-name", "recovery.json", "-o", "-name", "session.json", ")", "-print"],
            capture_output=True, text=True, timeout=15, check=False,
        )
        return [Path(x) for x in res.stdout.splitlines() if x.strip()]
    except Exception as exc:
        log(f"state search failed: {exc}")
        return []


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
    sub_dir = STAGE / "subscribes"
    for d in (media_dir, audio_dir, fx_dir, sub_dir):
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

    active_src_iter = iter(info["subscribe_paths"])
    sub_idx = 0
    for sub in staged.get("subscribes") or []:
        if not isinstance(sub, dict) or not sub.get("enabled") or not str(sub.get("source") or "").strip():
            continue
        src = next(active_src_iter)
        sub_idx += 1
        dst = cp(src, sub_dir / f"subscribe{sub_idx:02d}{src.suffix.lower()}")
        sub["source"] = str(dst)

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
    settings = info["data"].get("settings") or {}
    values = {
        "SIDE": str(side),
        "IMG": str(image),
        "FX1": str(fx[0]),
        "FX2": str(fx[1]),
        "AUDIO_COUNT": str(len(info["audios"])),
        "EFFECT_COUNT": str(len(fx)),
        "SUBSCRIBE_COUNT": str(len(info["subscribe_paths"])),
        "PROJECT_NAME": str(project.get("name") or ""),
        "PROJECT_ID": str(project.get("id") or UUID),
        "DURATION_HOURS": str(settings.get("durationHours", 2.0)),
    }
    log(f"selected real fixture side={side}")
    log(f"project={values['PROJECT_NAME']!r} media=1 audio=15 effects={len(fx)} active_subscribes={len(info['subscribe_paths'])}")
    if ENV_FILE:
        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        ENV_FILE.write_text("\n".join(f"{k}={shlex.quote(v)}" for k, v in values.items()) + "\n")
    else:
        print(json.dumps(values, ensure_ascii=False, indent=2))


def try_candidate(side: Path):
    if not side.is_file():
        return False
    info, reason = validate_side(side)
    if not info:
        if UUID in str(side):
            log(f"exact-UUID side rejected {side}: {reason}")
        return False
    try:
        info = stage_fixture(info)
    except Exception as exc:
        log(f"staging failed; using original real fixture: {exc}")
    emit(info)
    return True


maybe_mount_known_volume()

# 1) While TOSHIBA is mounted, refresh from the physical exact batch first.
# This is intentional: an older durable fixture may predate Subscribe staging.
if KNOWN_BATCH.is_dir():
    physical = sorted(KNOWN_BATCH.glob("**/Rendered/logs/*project.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for side in physical:
        if try_candidate(side):
            raise SystemExit(0)

# 2) Explicit caller-supplied side file.
explicit = os.environ.get("ENDLUME_E2E_SIDE")
if explicit and try_candidate(Path(os.path.expanduser(explicit))):
    raise SystemExit(0)

# 3) Durable staged copy from a previous successful physical discovery.
staged_side = STAGE / "project.json"
if staged_side.is_file():
    info, reason = validate_side(staged_side)
    if info:
        log("using previously staged durable real fixture")
        emit(info)
        raise SystemExit(0)
    log(f"staged fixture rejected: {reason}")

# 4) Search common local/macOS locations.
candidates = []
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
    if try_candidate(side):
        raise SystemExit(0)

# 5) Recover a compatible real project snapshot from ENDLUME persisted state.
for state in state_candidates():
    try:
        raw = json.loads(state.read_text(errors="replace"))
    except Exception:
        continue
    for obj in walk_side_like(raw):
        temp = write_state_candidate(state, obj)
        if try_candidate(temp):
            raise SystemExit(0)

log("NO VALID REAL 1-image + 15-audio + >=2-effects fixture found")
log("Volumes now: " + (", ".join(p.name for p in Path('/Volumes').iterdir()) if Path('/Volumes').is_dir() else "Volumes directory unavailable"))
log("Connect/mount the real project drive once; a successful run stages a durable local CI copy under ~/.endlume-ci-fixtures")
raise SystemExit(2)
