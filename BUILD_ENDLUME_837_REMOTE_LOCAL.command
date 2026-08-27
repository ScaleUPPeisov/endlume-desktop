#!/bin/bash
set -Eeuo pipefail
REPO="ScaleUPPeisov/endlume-desktop"
VERSION="1.0.0-alpha.8.37"
TAG="endlume-v1.0.0-alpha.8.37"
ASSET="ENDLUME-Studio-1.0.0-alpha.8.37-macos-arm64.zip"
CHECKSUM="$ASSET.sha256"
DEST="/Applications/ENDLUME Studio.app"
NEW="/Applications/.ENDLUME Studio.remote-new.app"
OLD="/Applications/.ENDLUME Studio.remote-previous.app"
TMP="$(mktemp -d /tmp/endlume-837-remote.XXXXXX)"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo "❌ ENDLUME 8.37 remote bootstrap: $1" >&2; exit 1; }
stage(){ echo "@@ENDLUME_STAGE|$1"; echo "@@ENDLUME_PROGRESS|$2"; echo "$1"; }

[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"

stage "Скачиваю готовую ENDLUME $VERSION" 15
gh release download "$TAG" --repo "$REPO" --pattern "$ASSET" --pattern "$CHECKSUM" --dir "$TMP" --clobber || fail "готовый release ещё не опубликован"
test -s "$TMP/$ASSET" || fail "ZIP не скачан"
test -s "$TMP/$CHECKSUM" || fail "checksum не скачан"

stage "Проверяю SHA-256" 35
(cd "$TMP" && /usr/bin/shasum -a 256 -c "$CHECKSUM") || fail "SHA-256 не совпал"

stage "Проверяю приложение" 55
mkdir -p "$TMP/stage"
/usr/bin/ditto -x -k "$TMP/$ASSET" "$TMP/stage"
APP="$(/usr/bin/find "$TMP/stage" -maxdepth 4 -type d -name 'ENDLUME Studio.app' -print -quit)"
test -n "$APP" && test -d "$APP" || fail "ENDLUME Studio.app не найдена в ZIP"
BUNDLE_ID="$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$APP/Contents/Info.plist")"
APP_VERSION="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$APP/Contents/Info.plist")"
[[ "$BUNDLE_ID" == "studio.endlume.desktop" ]] || fail "неверный Bundle ID: $BUNDLE_ID"
[[ "$APP_VERSION" == "$VERSION" ]] || fail "неверная версия: $APP_VERSION"
/usr/bin/codesign --verify --deep --strict "$APP" || fail "codesign проверка не пройдена"

stage "Подготавливаю установку" 72
rm -rf "$NEW" "$OLD" >/dev/null 2>&1 || true
/usr/bin/ditto "$APP" "$NEW" || fail "не удалось подготовить новую .app"

stage "Устанавливаю и перезапускаю" 86
/usr/bin/osascript -e 'tell application "ENDLUME Studio" to quit' >/dev/null 2>&1 || true
for _ in $(seq 1 40); do /usr/bin/pgrep -x "ENDLUME Studio" >/dev/null 2>&1 || break; /bin/sleep 0.25; done
if [[ -d "$DEST" ]]; then /bin/mv "$DEST" "$OLD" || fail "не удалось подготовить rollback"; fi
if /bin/mv "$NEW" "$DEST"; then :; else [[ -d "$OLD" ]] && /bin/mv "$OLD" "$DEST"; fail "atomic swap не выполнен"; fi
/usr/bin/xattr -dr com.apple.quarantine "$DEST" >/dev/null 2>&1 || true
/usr/bin/codesign --verify --deep --strict "$DEST" || { rm -rf "$DEST"; [[ -d "$OLD" ]] && /bin/mv "$OLD" "$DEST"; fail "финальная codesign проверка не пройдена"; }
FINAL_VERSION="$(/usr/bin/plutil -extract CFBundleShortVersionString raw -o - "$DEST/Contents/Info.plist")"
[[ "$FINAL_VERSION" == "$VERSION" ]] || { rm -rf "$DEST"; [[ -d "$OLD" ]] && /bin/mv "$OLD" "$DEST"; fail "финальная версия неверна"; }
open "$DEST"
/bin/sleep 2
rm -rf "$OLD" >/dev/null 2>&1 || true
stage "Готово — Remote Update Center установлен" 100
