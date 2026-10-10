#!/bin/bash
set -Eeuo pipefail
SRC="$GITHUB_WORKSPACE/qa/phase2-ui-v6.sh"
FIXED="$RUNNER_TEMP/phase2-ui-v7-wrapper.sh"
python3 - "$SRC" "$FIXED" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
# V6 raw Python string emitted two backslashes into JavaScript strings; JXA then
# returned literal "\\n" text. Reduce only doubled-backslash-n sequences to one
# backslash-n so osascript returns real line breaks and awk sees NAV_COUNT.
s=s.replace('\\\\n','\\n')
Path(sys.argv[2]).write_text(s)
PY
chmod +x "$FIXED"
exec bash "$FIXED"
