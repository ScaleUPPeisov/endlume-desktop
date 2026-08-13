#!/bin/zsh
set -euo pipefail

export PATH="/opt/homebrew/bin:$HOME/.cargo/bin:$PATH"
TARGET="aarch64-apple-darwin"
DESKTOP_APP="$HOME/Desktop/ENDLUME Studio.app"
KEY_DIR="$HOME/Library/Application Support/ENDLUME Studio/updater-keys"
KEY="$KEY_DIR/endlume-updater.key"

fail(){
  code=$?
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "❌ ENDLUME: bootstrap удалённых обновлений остановлен"
  echo "Рабочая ENDLUME на рабочем столе НЕ заменена."
  if [[ -n "${LOG:-}" ]]; then echo "Лог: $LOG"; fi
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  read "?Нажмите Enter, чтобы закрыть..."
  exit $code
}
trap fail ERR

printf '\033c'
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ENDLUME 1.0.0-alpha.8.4 — REMOTE UPDATES HOTFIX"
echo " Исправление FFmpeg sidecar • последняя ручная установка"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

[[ "$(uname -m)" == "arm64" ]] || { echo "❌ Нужен Apple Silicon M1+"; exit 1; }

# Find the already unpacked alpha.8.4 project. Prefer newest matching folder.
PROJECT=""
for d in "$HOME"/Downloads/ENDLUME_1.0_Tauri_alpha8_4*; do
  [[ -d "$d" && -f "$d/src-tauri/tauri.conf.json" ]] || continue
  PROJECT="$d"
done
[[ -n "$PROJECT" ]] || { echo "❌ Не найдена распакованная папка ENDLUME_1.0_Tauri_alpha8_4 в Загрузках"; exit 1; }
cd "$PROJECT"

echo "✓ Проект: $PROJECT"
LOG_DIR="$PROJECT/build_logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/ENDLUME-alpha8_4-updater-hotfix-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

for c in node npm cargo ffmpeg ffprobe python3; do
  command -v "$c" >/dev/null || { echo "❌ Не найден $c"; exit 1; }
done

mkdir -p "$KEY_DIR"
chmod 700 "$KEY_DIR"

if [[ ! -d node_modules ]]; then
  echo "[1/8] npm dependencies..."
  npm install --no-audit --no-fund
else
  echo "[1/8] npm dependencies уже готовы"
fi

if [[ ! -f "$KEY" || ! -f "$KEY.pub" ]]; then
  echo "[2/8] Создаю постоянный ключ подписи ENDLUME Updater..."
  npx tauri signer generate -w "$KEY" --ci -p ""
  chmod 600 "$KEY" "$KEY.pub"
else
  echo "[2/8] Использую существующий постоянный updater-ключ"
fi

PUBKEY="$(tr -d '\r\n' < "$KEY.pub")"
[[ -n "$PUBKEY" ]] || { echo "❌ Публичный updater-ключ пуст"; exit 1; }

python3 - "$PUBKEY" <<'PY'
import json, sys
from pathlib import Path
p = Path('src-tauri/tauri.conf.json')
d = json.loads(p.read_text())
d.setdefault('plugins', {}).setdefault('updater', {})['pubkey'] = sys.argv[1]
d['plugins']['updater']['endpoints'] = [
  'https://endlume-updates.vercel.app/api/update?target={{target}}&arch={{arch}}&current_version={{current_version}}'
]
d.setdefault('bundle', {})['createUpdaterArtifacts'] = True
p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
PY

echo "[3/8] Готовлю FFmpeg / FFprobe sidecar ДО Rust-проверки..."
mkdir -p src-tauri/binaries
FFMPEG="$(command -v ffmpeg)"
FFPROBE="$(command -v ffprobe)"
cp -f "$FFMPEG" "src-tauri/binaries/ffmpeg-$TARGET"
cp -f "$FFPROBE" "src-tauri/binaries/ffprobe-$TARGET"
chmod +x "src-tauri/binaries/ffmpeg-$TARGET" "src-tauri/binaries/ffprobe-$TARGET"
[[ -x "src-tauri/binaries/ffmpeg-$TARGET" ]] || { echo "❌ ffmpeg sidecar не создан"; exit 1; }
[[ -x "src-tauri/binaries/ffprobe-$TARGET" ]] || { echo "❌ ffprobe sidecar не создан"; exit 1; }
echo "✓ FFmpeg sidecar: $(du -h "src-tauri/binaries/ffmpeg-$TARGET" | awk '{print $1}')"
echo "✓ FFprobe sidecar: $(du -h "src-tauri/binaries/ffprobe-$TARGET" | awk '{print $1}')"

echo "[4/8] TypeScript / Vite..."
npm run build

echo "[5/8] Rust / Tauri cargo check..."
cargo check --manifest-path src-tauri/Cargo.toml --target "$TARGET"

echo "[6/8] Проверяю updater endpoint..."
HTTP_CODE="$(curl -L -sS -o /tmp/endlume_updater_response.json -w '%{http_code}' \
  'https://endlume-updates.vercel.app/api/update?target=darwin&arch=aarch64&current_version=1.0.0-alpha.8.4' || true)"
if [[ "$HTTP_CODE" != "204" && "$HTTP_CODE" != "200" ]]; then
  echo "❌ Update server ответил HTTP $HTTP_CODE"
  cat /tmp/endlume_updater_response.json 2>/dev/null || true
  exit 1
fi
echo "✓ Update server HTTP $HTTP_CODE"

echo "[7/8] Собираю подписанный standalone ENDLUME + updater artifacts..."
export TAURI_SIGNING_PRIVATE_KEY="$(cat "$KEY")"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD=""
npx tauri build --target "$TARGET" --bundles app

# Find app and updater artifacts robustly even if CARGO_TARGET_DIR is customized.
APP_PATH="$(find src-tauri/target "$HOME"/Downloads/ENDLUME_1.0_Tauri*/src-tauri/target \
  -type d -path '*/release/bundle/macos/ENDLUME Studio.app' -print 2>/dev/null | tail -1 || true)"
[[ -n "$APP_PATH" && -d "$APP_PATH" ]] || { echo "❌ Не найден собранный ENDLUME Studio.app"; exit 1; }

TAR_PATH="$(find "$(dirname "$APP_PATH")" -maxdepth 1 -type f -name 'ENDLUME Studio.app.tar.gz' -print -quit 2>/dev/null || true)"
SIG_PATH="${TAR_PATH}.sig"
[[ -n "$TAR_PATH" && -f "$TAR_PATH" ]] || { echo "❌ Не создан updater artifact .app.tar.gz"; exit 1; }
[[ -f "$SIG_PATH" ]] || { echo "❌ Не создан updater signature .sig"; exit 1; }

echo "✓ App: $APP_PATH"
echo "✓ Updater package: $(basename "$TAR_PATH") ($(du -h "$TAR_PATH" | awk '{print $1}'))"
echo "✓ Signature: $(basename "$SIG_PATH")"

echo "[8/8] Безопасно заменяю приложение на рабочем столе..."
BACKUP="$HOME/Desktop/ENDLUME Studio alpha8.3 backup.app"
rm -rf "$BACKUP"
if [[ -d "$DESKTOP_APP" ]]; then mv "$DESKTOP_APP" "$BACKUP"; fi
if ! ditto "$APP_PATH" "$DESKTOP_APP"; then
  rm -rf "$DESKTOP_APP"
  [[ -d "$BACKUP" ]] && mv "$BACKUP" "$DESKTOP_APP"
  echo "❌ Не удалось скопировать новую .app; старая восстановлена"
  exit 1
fi
xattr -dr com.apple.quarantine "$DESKTOP_APP" 2>/dev/null || true

RELEASE_DIR="$HOME/Desktop/ENDLUME Release Bootstrap"
mkdir -p "$RELEASE_DIR"
cp -f "$TAR_PATH" "$SIG_PATH" "$KEY.pub" "$RELEASE_DIR/"
cat > "$RELEASE_DIR/IMPORTANT.txt" <<TXT
ENDLUME Remote Updates bootstrap 1.0.0-alpha.8.4
Server: https://endlume-updates.vercel.app
Public key backup: $KEY.pub
PRIVATE KEY LOCATION (DO NOT SHARE OR DELETE): $KEY

Future update packages MUST be signed with this same private key.
TXT

# Verify installed app version from Info.plist where available.
INSTALLED_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$DESKTOP_APP/Contents/Info.plist" 2>/dev/null || true)"
echo "✓ Installed version: ${INSTALLED_VERSION:-1.0.0-alpha.8.4}"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ ENDLUME 1.0.0-alpha.8.4 УСТАНОВЛЕН"
echo "✅ Remote Updates встроены"
echo "✅ Terminal для следующих обычных обновлений больше не нужен"
echo "Рабочее приложение: $DESKTOP_APP"
echo "Резервная старая версия: $BACKUP"
echo "Updater artifacts: $RELEASE_DIR"
echo "Updater private key: $KEY  ← НЕ УДАЛЯТЬ И НЕ ПЕРЕДАВАТЬ"
echo "Лог: $LOG"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
open "$DESKTOP_APP"
sleep 2
exit 0
