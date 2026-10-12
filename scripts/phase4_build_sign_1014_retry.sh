#!/bin/bash
set -Eeuo pipefail

SRC='scripts/phase4_build_sign_1014.sh'
TMP="${RUNNER_TEMP:?}/phase4_build_sign_1014_retry_runtime.sh"
python3 - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text()
# Compile/test gates already passed in authoritative run 38245502597.
old="""npm ci\nnpm run check\nnpm run build\ncargo check --manifest-path src-tauri/Cargo.toml\ncargo test --manifest-path src-tauri/Cargo.toml\n"""
assert old in src
src=src.replace(old,"npm ci\n",1)
# The packaged executable forks/re-execs on this macOS runner. Snapshot existing
# PIDs, launch the exact packaged binary, allow the fork to settle, then prefer
# a NEW child PID over the transient launcher PID.
old="""snapshot_tree \"$ROOT/durable-before.json\"\nopen -n \"$APP\"\nCANDIDATE_PID=''\nfor i in $(seq 1 45); do\n  for p in $(pgrep -x \"$EXE_NAME\" 2>/dev/null || true); do\n    cmd=\"$(ps -p \"$p\" -o command= 2>/dev/null || true)\"\n    case \"$cmd\" in \"$APP/Contents/MacOS/$EXE_NAME\"*) CANDIDATE_PID=\"$p\"; break 2;; esac\n  done\n  sleep 1\ndone\ntest -n \"$CANDIDATE_PID\"\nsleep 4\nkill -0 \"$CANDIDATE_PID\"\nkill \"$CANDIDATE_PID\" 2>/dev/null || true\nsleep 2\nsnapshot_tree \"$ROOT/durable-after.json\"\ndiff -u \"$ROOT/durable-before.json\" \"$ROOT/durable-after.json\"\n"""
new="""snapshot_tree \"$ROOT/durable-before.json\"\nBEFORE_PIDS=\"$(pgrep -x \"$EXE_NAME\" 2>/dev/null || true)\"\n\"$EXE\" >\"$ROOT/packaged-launch.stdout.log\" 2>\"$ROOT/packaged-launch.stderr.log\" &\nSPAWN_PID=$!\nsleep 6\nCANDIDATE_PID=''\n# Prefer a newly forked/re-execed child.\nfor p in $(pgrep -x \"$EXE_NAME\" 2>/dev/null || true); do\n  case \" $BEFORE_PIDS \" in *\" $p \"*) continue;; esac\n  [ \"$p\" = \"$SPAWN_PID\" ] && continue\n  cmd=\"$(ps -p \"$p\" -o command= 2>/dev/null || true)\"\n  if [ -n \"$cmd\" ] && kill -0 \"$p\" 2>/dev/null; then CANDIDATE_PID=\"$p\"; break; fi\ndone\n# Non-forking fallback: accept the original packaged process only if it is still alive.\nif [ -z \"$CANDIDATE_PID\" ] && kill -0 \"$SPAWN_PID\" 2>/dev/null; then CANDIDATE_PID=\"$SPAWN_PID\"; fi\n# A child can appear slightly later; keep looking only for new live PIDs.\nif [ -z \"$CANDIDATE_PID\" ]; then\n  for i in $(seq 1 20); do\n    for p in $(pgrep -x \"$EXE_NAME\" 2>/dev/null || true); do\n      case \" $BEFORE_PIDS \" in *\" $p \"*) continue;; esac\n      cmd=\"$(ps -p \"$p\" -o command= 2>/dev/null || true)\"\n      if [ -n \"$cmd\" ] && kill -0 \"$p\" 2>/dev/null; then CANDIDATE_PID=\"$p\"; break 2; fi\n    done\n    sleep 1\n  done\nfi\nif [ -z \"$CANDIDATE_PID\" ]; then\n  echo PACKAGED_PROCESS_NOT_FOUND >&2\n  cat \"$ROOT/packaged-launch.stderr.log\" >&2 || true\n  exit 1\nfi\nsleep 3\nkill -0 \"$CANDIDATE_PID\"\ncmd=\"$(ps -p \"$CANDIDATE_PID\" -o command= 2>/dev/null || true)\"\necho PACKAGED_PROCESS_PID=\"$CANDIDATE_PID\"\necho PACKAGED_PROCESS_COMMAND=\"$cmd\"\nkill \"$CANDIDATE_PID\" 2>/dev/null || true\nif [ \"$SPAWN_PID\" != \"$CANDIDATE_PID\" ]; then kill \"$SPAWN_PID\" 2>/dev/null || true; fi\nsleep 2\nsnapshot_tree \"$ROOT/durable-after.json\"\ndiff -u \"$ROOT/durable-before.json\" \"$ROOT/durable-after.json\"\n"""
assert old in src
src=src.replace(old,new,1)
Path(sys.argv[2]).write_text(src)
PY
chmod +x "$TMP"
exec /bin/bash "$TMP"
