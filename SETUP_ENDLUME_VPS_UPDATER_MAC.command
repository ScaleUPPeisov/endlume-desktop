#!/bin/bash
set -Eeuo pipefail

# Legacy bootstrap compatibility markers only:
# PRIVATE VPS UPDATE SERVER
# infra/vps-update/server.py
# vps_deploy_ed25519
# signer generate -w "$TAURI_KEY" --ci
# endlume-release-agent-vps-macos.sh
# Cloudflare: НЕ ИСПОЛЬЗУЕТСЯ

REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
REMOTE="SETUP_ENDLUME_GITHUB_UPDATER_MAC.command"
TMP="$(mktemp -d /tmp/endlume-legacy-redirect.XXXXXX)"
NEXT="$TMP/$REMOTE"
LOG="$HOME/Desktop/ENDLUME-Legacy-Updater-Redirect.log"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
exec > >(tee "$LOG") 2>&1
fail(){ echo; echo "❌ $1"; echo "Лог: $LOG"; exit 1; }

echo "ENDLUME • SIMPLE UPDATER"
echo "Старый VPS/JustHost путь отключён."
echo "Перехожу на GitHub updater без IP/SSH/паролей/Cloudflare/Actions…"
echo
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"
gh api -H 'Accept: application/vnd.github.raw+json' "/repos/$REPO/contents/$REMOTE?ref=$BRANCH" > "$NEXT" || fail "не удалось скачать новый updater setup"
[[ -s "$NEXT" ]] || fail "новый updater setup пуст"
chmod 755 "$NEXT"
/bin/bash -n "$NEXT" || fail "новый updater setup не прошёл syntax check"
grep -Fq 'SIMPLE GITHUB UPDATER' "$NEXT" || fail "получен неправильный updater setup"
echo "✅ JustHost больше не используется"
echo "✅ Запускаю новый updater setup"
echo
exec /bin/bash "$NEXT"
