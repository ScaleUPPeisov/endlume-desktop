#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="10.0.5"
BROKEN_SHA="d6c261f96c883095850d1453e5ca513ff48f62cb"
export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.cargo/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export CARGO_TARGET_DIR="$HOME/.endlume-build-cache/target-1005-candidate"
STAGE="$RUNNER_TEMP/endlume-1005-candidate"
FINAL="$GITHUB_WORKSPACE/candidate-1005"
ZIP_NAME="ENDLUME-YT-Studio-PEISOV-10.0.5-macOS-ARM64-CANDIDATE.zip"
rm -rf "$STAGE" "$FINAL"
mkdir -p "$STAGE" "$FINAL"

echo "=== SOURCE + REGRESSION LOCK ==="
node scripts/assert-production-main-window.mjs
python3 - <<'PY'
import json,re,subprocess
from pathlib import Path
v="10.0.5"
assert json.load(open("package.json"))["version"]==v
assert json.load(open("package-lock.json"))["version"]==v
assert json.load(open("src-tauri/tauri.conf.json"))["version"]==v
assert re.search(r'^version = "10[.]0[.]5"$',Path("src-tauri/Cargo.toml").read_text(),re.M)
lock=Path("src-tauri/Cargo.lock").read_text()
assert 'name = "endlume"\nversion = "10.0.5"' in lock
cfg=json.load(open("src-tauri/tauri.conf.json"))
wins=cfg.get("app",{}).get("windows",[])
assert isinstance(wins,list) and len(wins)>0
assert sum(1 for w in wins if w.get("label")=="main")==1
changed=subprocess.check_output(["git","diff","--name-only","d6c261f96c883095850d1453e5ca513ff48f62cb","HEAD"],text=True).splitlines()
forbidden=[
  "src-tauri/src/render.rs","src-tauri/src/live_preview.rs","src-tauri/src/model.rs",
  "src/store.ts","src/tauri.ts","src/styles.css"
]
bad=[p for p in changed if p in forbidden or p.startswith("src/pages/") or p.startswith("src/components/")]
assert not bad,("REGRESSION_LOCK_VIOLATION",bad)
print("ENDLUME_1005_SOURCE_AND_MAIN_WINDOW_GREEN",changed)
PY

echo "=== STAGE NATIVE FFMPEG ==="
mkdir -p src-tauri/binaries
if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
  cp -L "$(command -v ffmpeg)" src-tauri/binaries/ffmpeg-aarch64-apple-darwin
  cp -L "$(command -v ffprobe)" src-tauri/binaries/ffprobe-aarch64-apple-darwin
else
  FOUNDATION="$HOME/.endlume-local-builder/endlume-desktop-8.40-bootstrap"
  test -x "$FOUNDATION/src-tauri/binaries/ffmpeg-aarch64-apple-darwin"
  test -x "$FOUNDATION/src-tauri/binaries/ffprobe-aarch64-apple-darwin"
  cp "$FOUNDATION/src-tauri/binaries/ffmpeg-aarch64-apple-darwin" src-tauri/binaries/
  cp "$FOUNDATION/src-tauri/binaries/ffprobe-aarch64-apple-darwin" src-tauri/binaries/
fi
chmod +x src-tauri/binaries/ffmpeg-aarch64-apple-darwin src-tauri/binaries/ffprobe-aarch64-apple-darwin
/usr/bin/file src-tauri/binaries/ffmpeg-aarch64-apple-darwin
/usr/bin/otool -L src-tauri/binaries/ffmpeg-aarch64-apple-darwin | head -25

echo "=== RESOLVE APPLE PRODUCTION SIGNING IDENTITY ==="
IDENTITIES="$(/usr/bin/security find-identity -v -p codesigning 2>&1 || true)"
printf '%s\n' "$IDENTITIES" | sed -E 's/[0-9A-F]{40}/[HASH]/g'
IDENTITY="$(printf '%s\n' "$IDENTITIES" | grep 'Developer ID Application:' | head -1 | sed -E 's/.*"([^"]+)".*/\1/' || true)"
if test -n "$IDENTITY"; then
  export APPLE_SIGNING_IDENTITY="$IDENTITY"
  SIGNING_MODE="developer-id"
  echo "ENDLUME_1005_DEVELOPER_ID_FOUND=$IDENTITY"
else
  export APPLE_SIGNING_IDENTITY="-"
  SIGNING_MODE="adhoc"
  echo "ENDLUME_1005_DEVELOPER_ID_MISSING"
fi
printf '%s' "$SIGNING_MODE" > "$STAGE/signing-mode.txt"

echo "=== APPLE NOTARY ENV PRESENCE (NAMES ONLY) ==="
for N in APPLE_ID APPLE_PASSWORD APPLE_TEAM_ID APPLE_API_KEY APPLE_API_ISSUER APPLE_API_KEY_PATH; do
  if printenv "$N" >/dev/null 2>&1; then echo "$N=PRESENT"; else echo "$N=ABSENT"; fi
done

echo "=== FRONTEND + RUST REGRESSION ==="
npm ci
npm run check
npm run build
cargo check --manifest-path src-tauri/Cargo.toml
cargo test --manifest-path src-tauri/Cargo.toml -- --nocapture

echo "=== BUILD CANDIDATE WITH MAIN WINDOW PRESERVED ==="
python3 - <<'PY'
import json
from pathlib import Path
p=Path("src-tauri/tauri.conf.json")
d=json.loads(p.read_text())
d["bundle"]["createUpdaterArtifacts"]=False
wins=d.get("app",{}).get("windows",[])
assert isinstance(wins,list) and wins and any(w.get("label")=="main" for w in wins)
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n")
PY
node scripts/assert-production-main-window.mjs
npm run tauri build -- --bundles app --features e2e-render
BUILD_APP="$(find "$CARGO_TARGET_DIR/release/bundle/macos" -maxdepth 1 -type d -name '*.app' -print -quit)"
test -n "$BUILD_APP" -a -d "$BUILD_APP"
test "$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$BUILD_APP/Contents/Info.plist")" = "$VERSION"
test "$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$BUILD_APP/Contents/Info.plist")" = "studio.endlume.desktop"

echo "=== PRODUCTION SIGNATURE INSPECTION ==="
/usr/bin/codesign --verify --deep --strict --verbose=2 "$BUILD_APP"
if /usr/bin/codesign -dv --verbose=4 "$BUILD_APP" 2>&1 | grep -q 'Authority=Developer ID Application:'; then
  echo PASS > "$STAGE/developer-id.txt"
else
  echo FAIL > "$STAGE/developer-id.txt"
fi

echo "=== NOTARIZATION / STAPLE EXISTING OR STANDARD TAURI CREDENTIALS ==="
NOTARY_STATUS="FAIL"
if /usr/bin/xcrun stapler validate "$BUILD_APP" >/tmp/e1005-stapler-before.log 2>&1; then
  NOTARY_STATUS="PASS"
  cat /tmp/e1005-stapler-before.log
else
  NOTARY_ZIP="$STAGE/notary-submit.zip"
  /usr/bin/ditto -c -k --sequesterRsrc --keepParent "$BUILD_APP" "$NOTARY_ZIP"
  if printenv APPLE_ID >/dev/null 2>&1 && printenv APPLE_PASSWORD >/dev/null 2>&1 && printenv APPLE_TEAM_ID >/dev/null 2>&1; then
    APPLE_ID_VALUE="$(printenv APPLE_ID)"
    APPLE_PASSWORD_VALUE="$(printenv APPLE_PASSWORD)"
    APPLE_TEAM_VALUE="$(printenv APPLE_TEAM_ID)"
    if /usr/bin/xcrun notarytool submit "$NOTARY_ZIP" --apple-id "$APPLE_ID_VALUE" --password "$APPLE_PASSWORD_VALUE" --team-id "$APPLE_TEAM_VALUE" --wait; then
      /usr/bin/xcrun stapler staple "$BUILD_APP"
      /usr/bin/xcrun stapler validate "$BUILD_APP"
      NOTARY_STATUS="PASS"
    fi
    unset APPLE_ID_VALUE APPLE_PASSWORD_VALUE APPLE_TEAM_VALUE
  elif printenv APPLE_API_KEY_PATH >/dev/null 2>&1 && printenv APPLE_API_KEY >/dev/null 2>&1 && printenv APPLE_API_ISSUER >/dev/null 2>&1; then
    API_KEY_PATH="$(printenv APPLE_API_KEY_PATH)"
    API_KEY_ID="$(printenv APPLE_API_KEY)"
    API_ISSUER="$(printenv APPLE_API_ISSUER)"
    if /usr/bin/xcrun notarytool submit "$NOTARY_ZIP" --key "$API_KEY_PATH" --key-id "$API_KEY_ID" --issuer "$API_ISSUER" --wait; then
      /usr/bin/xcrun stapler staple "$BUILD_APP"
      /usr/bin/xcrun stapler validate "$BUILD_APP"
      NOTARY_STATUS="PASS"
    fi
    unset API_KEY_PATH API_KEY_ID API_ISSUER
  else
    echo "ENDLUME_1005_NOTARY_CREDENTIALS_NOT_AVAILABLE_IN_RUNNER_ENV"
  fi
fi
printf '%s' "$NOTARY_STATUS" > "$STAGE/notarization.txt"

echo "=== CREATE THE EXACT CANDIDATE ZIP ==="
cp -R "$BUILD_APP" "$STAGE/ENDLUME YT Studio PEISOV.app"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$STAGE/ENDLUME YT Studio PEISOV.app" "$FINAL/$ZIP_NAME"
/usr/bin/shasum -a 256 "$FINAL/$ZIP_NAME" | tee "$FINAL/$ZIP_NAME.sha256"

echo "=== UNPACK EXACT ZIP COPY #1 FOR REAL LAUNCH ==="
LAUNCH_UNPACK="$GITHUB_WORKSPACE/.qa-1005-launch-unpack"
rm -rf "$LAUNCH_UNPACK"
mkdir -p "$LAUNCH_UNPACK"
/usr/bin/ditto -x -k "$FINAL/$ZIP_NAME" "$LAUNCH_UNPACK"
LAUNCH_APP="$(find "$LAUNCH_UNPACK" -maxdepth 2 -type d -name '*.app' -print -quit)"
test -n "$LAUNCH_APP" -a -d "$LAUNCH_APP"
LAUNCH_EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$LAUNCH_APP/Contents/Info.plist")"
LAUNCH_BIN="$LAUNCH_APP/Contents/MacOS/$LAUNCH_EXE"
test -x "$LAUNCH_BIN"
test "$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$LAUNCH_APP/Contents/Info.plist")" = "$VERSION"
test "$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$LAUNCH_APP/Contents/Info.plist")" = "studio.endlume.desktop"
/usr/bin/lipo -archs "$LAUNCH_BIN" | grep -qw arm64

echo "=== REAL PACKAGED APP LAUNCH + MAIN UI SMOKE ==="
MARKER="$STAGE/frontend-main.json"
STAMP="$STAGE/launch-start.stamp"
SHOT="$FINAL/ENDLUME-10.0.5-main-ui-smoke.png"
rm -f "$MARKER" "$SHOT"
touch "$STAMP"
/bin/launchctl setenv ENDLUME_LAUNCH_SMOKE_MARKER "$MARKER"
cleanup_launch_env(){ /bin/launchctl unsetenv ENDLUME_LAUNCH_SMOKE_MARKER >/dev/null 2>&1 || true; }
trap cleanup_launch_env EXIT
/usr/bin/open -n "$LAUNCH_APP"
for I in $(seq 1 60); do
  test -s "$MARKER" && break
  sleep 0.25
done
test -s "$MARKER"
cleanup_launch_env
cat "$MARKER"
PID="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));assert d["label"]=="main";assert d["frontendLoaded"] is True;print(d["pid"])' "$MARKER")"
kill -0 "$PID"
sleep 2
kill -0 "$PID"
WINDOW_COUNT="$(/usr/bin/osascript <<OSA
tell application "System Events"
  set p to first application process whose unix id is $PID
  set frontmost of p to true
  return count of windows of p
end tell
OSA
)"
echo "ENDLUME_1005_WINDOW_COUNT=$WINDOW_COUNT"
test "$WINDOW_COUNT" -ge 1
/usr/sbin/screencapture -x "$SHOT"
test -s "$SHOT"
SHOT_BYTES="$(stat -f '%z' "$SHOT")"
echo "ENDLUME_1005_SCREENSHOT_BYTES=$SHOT_BYTES"
test "$SHOT_BYTES" -gt 10000
if test -d "$HOME/Library/Logs/DiagnosticReports"; then
  if find "$HOME/Library/Logs/DiagnosticReports" -type f -newer "$STAMP" -iname '*endlume*' -print | grep -q .; then
    echo "ENDLUME_1005_CRASH_REPORT_DETECTED" >&2
    find "$HOME/Library/Logs/DiagnosticReports" -type f -newer "$STAMP" -iname '*endlume*' -print >&2
    exit 31
  fi
fi
echo "ENDLUME_1005_REAL_LAUNCH_GREEN pid=$PID label=main windows=$WINDOW_COUNT"
kill "$PID" >/dev/null 2>&1 || true
sleep 1

echo "=== UNPACK EXACT SAME ZIP COPY #2 FOR RUNTIME / RENDER / SIGNING ==="
RUNTIME_UNPACK="$GITHUB_WORKSPACE/.qa-1005-runtime-unpack"
rm -rf "$RUNTIME_UNPACK"
mkdir -p "$RUNTIME_UNPACK"
/usr/bin/ditto -x -k "$FINAL/$ZIP_NAME" "$RUNTIME_UNPACK"
APP="$(find "$RUNTIME_UNPACK" -maxdepth 2 -type d -name '*.app' -print -quit)"
test -n "$APP" -a -d "$APP"
EXE="$(/usr/bin/plutil -extract CFBundleExecutable raw -o - "$APP/Contents/Info.plist")"
APP_BIN="$APP/Contents/MacOS/$EXE"
test -x "$APP_BIN"
test "$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$APP/Contents/Info.plist")" = "$VERSION"
test "$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$APP/Contents/Info.plist")" = "studio.endlume.desktop"
/usr/bin/lipo -archs "$APP_BIN" | grep -qw arm64

echo "=== EXACT UNPACKED APP COPY #2: FFMPEG + EFFECTS + SUBSCRIBE ==="
ENDLUME_APP_PATH="$APP" node scripts/verify-macos-ffmpeg-bundle.mjs | tee "$FINAL/ffmpeg-live-preview.log"
grep -q 'EFFECTS_LIVE_PREVIEW_RUNTIME_PASS' "$FINAL/ffmpeg-live-preview.log"
grep -q 'SUBSCRIBE_LIVE_PREVIEW_RUNTIME_PASS' "$FINAL/ffmpeg-live-preview.log"
grep -q 'ENDLUME_MACOS_FFMPEG_RUNTIME_PASS' "$FINAL/ffmpeg-live-preview.log"
echo "ENDLUME_1005_EFFECTS_SUBSCRIBE_FFMPEG_GREEN"

echo "=== EXACT UNPACKED APP COPY #2: REAL NORMAL RENDER ==="
python3 scripts/find-endlume-real-subscribe.py "$STAGE/subscribe.json"
FIXTURE_DIR="$(mktemp -d /tmp/e1005fixture.XXXXXX)"
python3 scripts/find-endlume-real-fixture.py "$FIXTURE_DIR/env"
source "$FIXTURE_DIR/env"
test "$AUDIO_COUNT" = 15
test "$EFFECT_COUNT" -ge 2
test -f "$SIDE"
OUT="$HOME/Movies/ENDLUME Studio/ENDLUME-1005-CANDIDATE-QA"
rm -rf "$OUT"
mkdir -p "$OUT"
ENDLUME_1000_OUTPUT_DIR="$OUT" \
ENDLUME_1000_COLD_LIMIT_SECONDS=60 \
ENDLUME_1000_WARM_LIMIT_SECONDS=60 \
ENDLUME_FINAL_MIN_BYTES=400000000 \
ENDLUME_FINAL_MAX_BYTES=600000000 \
python3 scripts/run-endlume-1000-render-job-e2e.py \
  "$SIDE" "$STAGE/subscribe.json" "$APP_BIN" "$APP/Contents/MacOS/ffmpeg" "$APP/Contents/MacOS/ffprobe" \
  "$FINAL/render-metrics.json"
python3 - <<'PY'
import json
d=json.load(open("candidate-1005/render-metrics.json"))
assert d["status"]=="passed" and d["release_gate"] is True,d
print("ENDLUME_1005_NORMAL_RENDER_GREEN",d)
PY
rm -rf "$OUT"

echo "=== EXACT UNPACKED APP COPY #2: CODESIGN / GATEKEEPER / STAPLER ==="
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP"
CODESIGN_STATUS="PASS"
if /usr/bin/codesign -dv --verbose=4 "$APP" 2>&1 | grep -q 'Authority=Developer ID Application:'; then
  PROD_SIGN_STATUS="PASS"
else
  PROD_SIGN_STATUS="FAIL"
fi
if /usr/sbin/spctl -a -vv "$APP" >"$FINAL/gatekeeper.log" 2>&1; then
  GATEKEEPER_STATUS="PASS"
else
  GATEKEEPER_STATUS="FAIL"
fi
cat "$FINAL/gatekeeper.log" || true
if /usr/bin/xcrun stapler validate "$APP" >"$FINAL/stapler.log" 2>&1; then
  STAPLER_STATUS="PASS"
else
  STAPLER_STATUS="FAIL"
fi
cat "$FINAL/stapler.log" || true

python3 - "$FINAL/qa-summary.json" "$CODESIGN_STATUS" "$PROD_SIGN_STATUS" "$GATEKEEPER_STATUS" "$STAPLER_STATUS" "$SIGNING_MODE" "$NOTARY_STATUS" <<'PY'
import json,sys,hashlib,pathlib
out,codesign,prod_sign,gatekeeper,stapler,signing_mode,notary=sys.argv[1:]
zip_path=pathlib.Path("candidate-1005/ENDLUME-YT-Studio-PEISOV-10.0.5-macOS-ARM64-CANDIDATE.zip")
summary={
  "version":"10.0.5",
  "brokenRelease":"10.0.4",
  "brokenCommit":"d6c261f96c883095850d1453e5ca513ff48f62cb",
  "mainWindowConfig":"PASS",
  "realLaunch":"PASS",
  "mainUiVisible":"PASS",
  "frontendLoaded":"PASS",
  "effectsLivePreview":"PASS",
  "subscribeLivePreview":"PASS",
  "ffmpegPortableRuntime":"PASS",
  "normalRender":"PASS",
  "codesign":codesign,
  "productionDeveloperIdSigning":prod_sign,
  "signingMode":signing_mode,
  "gatekeeper":gatekeeper,
  "notarization":stapler,
  "notaryDuringBuild":notary,
  "candidateZip":str(zip_path),
  "candidateSha256":hashlib.sha256(zip_path.read_bytes()).hexdigest()
}
summary["releaseReady"]=all(summary[k]=="PASS" for k in [
  "mainWindowConfig","realLaunch","mainUiVisible","frontendLoaded",
  "effectsLivePreview","subscribeLivePreview","ffmpegPortableRuntime",
  "normalRender","codesign","productionDeveloperIdSigning","gatekeeper","notarization"
])
pathlib.Path(out).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(summary,ensure_ascii=False,indent=2))
PY

cp "$STAGE/frontend-main.json" "$FINAL/frontend-main.json"
echo "CANDIDATE_APP_PATH=$APP" > "$FINAL/candidate-path.txt"

READY="$(python3 -c 'import json;print("1" if json.load(open("candidate-1005/qa-summary.json"))["releaseReady"] else "0")')"
if test "$READY" = "1"; then
  echo "ENDLUME_1005_CANDIDATE_RELEASE_READY"
else
  echo "ENDLUME_1005_CANDIDATE_NOT_RELEASE_READY" >&2
  exit 42
fi
