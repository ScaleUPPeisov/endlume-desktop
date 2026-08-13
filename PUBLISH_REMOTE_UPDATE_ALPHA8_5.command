#!/bin/zsh
set -euo pipefail
export PATH="/opt/homebrew/bin:$HOME/.cargo/bin:$PATH"
TARGET="aarch64-apple-darwin"
VERSION="1.0.0-alpha.8.5"
KEY_DIR="$HOME/Library/Application Support/ENDLUME Studio/updater-keys"
KEY="$KEY_DIR/endlume-updater.key"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$PROJECT_DIR/build_logs"
OUT_DIR="$HOME/Desktop/ENDLUME Remote Release $VERSION"
ZIP_OUT="$HOME/Desktop/ENDLUME_REMOTE_RELEASE_${VERSION}.zip"

fail(){
  code=$?
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "❌ ENDLUME: публикационный билд остановлен"
  echo "Текущая установленная ENDLUME НЕ изменялась."
  [[ -n "${LOG:-}" ]] && echo "Лог: $LOG"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  read "?Нажмите Enter, чтобы закрыть..."
  exit $code
}
trap fail ERR

printf '\033c'
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "ENDLUME $VERSION — OWNER REMOTE RELEASE BUILDER"
echo "Собираю и подписываю первое удалённое обновление"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

[[ "$(uname -m)" == "arm64" ]] || { echo "❌ Нужен Apple Silicon M1+"; exit 1; }
cd "$PROJECT_DIR"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/ENDLUME-release-${VERSION}-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

for c in node npm cargo ffmpeg ffprobe python3 ditto; do command -v "$c" >/dev/null || { echo "❌ Не найден $c"; exit 1; }; done
[[ -f "$KEY" && -f "$KEY.pub" ]] || { echo "❌ Не найден постоянный updater-ключ: $KEY"; echo "Сначала должна быть успешно установлена alpha.8.4 с Remote Updates."; exit 1; }

echo "[1/7] Переиспользую зависимости..."
if [[ ! -d node_modules ]]; then npm install --no-audit --no-fund; fi

echo "[2/7] Встраиваю тот же публичный updater-ключ..."
PUBKEY="$(tr -d '\r\n' < "$KEY.pub")"
python3 - "$PUBKEY" "$VERSION" <<'PY'
import json,sys,re
from pathlib import Path
pub,ver=sys.argv[1:]
p=Path('src-tauri/tauri.conf.json')
d=json.loads(p.read_text())
d['version']=ver
d.setdefault('plugins',{}).setdefault('updater',{})['pubkey']=pub
d['plugins']['updater']['endpoints']=['https://endlume-updates.vercel.app/api/update?target={{target}}&arch={{arch}}&current_version={{current_version}}']
d.setdefault('bundle',{})['createUpdaterArtifacts']=True
p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
p=Path('package.json'); j=json.loads(p.read_text()); j['version']=ver; p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n')
p=Path('src-tauri/Cargo.toml'); s=p.read_text(); s=re.sub(r'^version\s*=\s*"[^"]+"',f'version = "{ver}"',s,count=1,flags=re.M); p.write_text(s)
PY

echo "[3/7] Готовлю FFmpeg / FFprobe sidecar..."
mkdir -p src-tauri/binaries
cp -f "$(command -v ffmpeg)" "src-tauri/binaries/ffmpeg-$TARGET"
cp -f "$(command -v ffprobe)" "src-tauri/binaries/ffprobe-$TARGET"
chmod +x "src-tauri/binaries/ffmpeg-$TARGET" "src-tauri/binaries/ffprobe-$TARGET"

echo "[4/7] Проверяю UI..."
npm run build

echo "[5/7] Проверяю Rust/Tauri..."
cargo check --manifest-path src-tauri/Cargo.toml --target "$TARGET"

echo "[6/7] Собираю и подписываю updater artifact..."
export TAURI_SIGNING_PRIVATE_KEY="$(cat "$KEY")"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD=""
npx tauri build --target "$TARGET" --bundles app

APP_PATH="$(find src-tauri/target -type d -path '*/release/bundle/macos/ENDLUME Studio.app' -print 2>/dev/null | tail -1 || true)"
[[ -n "$APP_PATH" && -d "$APP_PATH" ]] || { echo "❌ Не найден ENDLUME Studio.app"; exit 1; }
TAR_PATH="$(find "$(dirname "$APP_PATH")" -maxdepth 1 -type f -name 'ENDLUME Studio.app.tar.gz' -print -quit 2>/dev/null || true)"
SIG_PATH="${TAR_PATH}.sig"
[[ -f "$TAR_PATH" ]] || { echo "❌ Не создан .app.tar.gz"; exit 1; }
[[ -f "$SIG_PATH" ]] || { echo "❌ Не создан .sig"; exit 1; }

echo "[7/7] Готовлю пакет публикации..."
rm -rf "$OUT_DIR" "$ZIP_OUT"
mkdir -p "$OUT_DIR"
cp -f "$TAR_PATH" "$SIG_PATH" "$KEY.pub" "$OUT_DIR/"
SIG_CONTENT="$(cat "$SIG_PATH")"
ARTIFACT_NAME="$(basename "$TAR_PATH")"
cat > "$OUT_DIR/release.json" <<JSON
{
  "version": "$VERSION",
  "pub_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "target": "darwin",
  "arch": "aarch64",
  "artifact": "$ARTIFACT_NAME",
  "signature": "$SIG_CONTENT",
  "notes": "13.08.2026 • ENDLUME $VERSION\nНовое уведомление об обновлении сверху слева.\nКнопки: Обновить / Обновить позже.\nПрогресс скачивания и установки прямо в уведомлении.\nПосле установки ENDLUME автоматически перезапускается."
}
JSON
cat > "$OUT_DIR/UPLOAD_ME.txt" <<TXT
Это ПОДПИСАННЫЙ удалённый релиз ENDLUME $VERSION.

Загрузите в чат ZIP:
$ZIP_OUT

НЕ ПЕРЕДАВАЙТЕ приватный ключ updater. Его здесь НЕТ.
Публичный .pub можно хранить вместе с релизом.
TXT
( cd "$HOME/Desktop" && ditto -c -k --sequesterRsrc --keepParent "$(basename "$OUT_DIR")" "$(basename "$ZIP_OUT")" )

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ REMOTE RELEASE $VERSION ГОТОВ"
echo "ZIP для публикации: $ZIP_OUT"
echo "Текущая ENDLUME на компьютере НЕ заменялась."
echo "После загрузки этого ZIP на update-сервер установленная alpha.8.4 увидит новое обновление."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
open "$HOME/Desktop"
read "?Нажмите Enter, чтобы закрыть..."
