#!/bin/bash
set -Eeuo pipefail

# ENDLUME • PRIVATE VPS UPDATE SERVER
# Compatibility/preflight markers used by the bootstrap:
# infra/vps-update/server.py
# vps_deploy_ed25519
# signer generate -w "$TAURI_KEY" --ci
# endlume-release-agent-vps-macos.sh

REPO="ScaleUPPeisov/endlume-desktop"
CORE_REF="1ac533867b3e148077f36cf2192f7ff39888e22d"
CORE_PATH="SETUP_ENDLUME_VPS_UPDATER_MAC.command"
VPS_HOST="188.94.191.240"
VPS_USER="root"
VPS_PORT="22"
VPS_LABEL="Paris / JustHost"
TMP="$(mktemp -d /tmp/endlume-vps-hostkey-fix.XXXXXX)"
CORE="$TMP/core.command"
SCAN="$TMP/hostkeys"
OLD="$TMP/old-hostkeys"
KNOWN="$HOME/.ssh/known_hosts"
LOG="$HOME/Desktop/ENDLUME-VPS-Updater-HostKey.log"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
exec > >(tee "$LOG") 2>&1
fail(){ echo; echo "❌ $1"; echo "Лог: $LOG"; exit 1; }

echo "ENDLUME • PRIVATE VPS UPDATE SERVER"
echo "Без Cloudflare • без карт • без GitHub Actions/Releases"
echo "Сервер: $VPS_LABEL"
echo "Адрес выбран автоматически: $VPS_HOST"
echo
[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"
for c in ssh ssh-keygen ssh-keyscan; do command -v "$c" >/dev/null 2>&1 || fail "$c не найден"; done

echo "0/8 Проверяю SSH identity Paris VPS…"
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
touch "$KNOWN"
chmod 600 "$KNOWN"

ssh-keyscan -T 10 -p "$VPS_PORT" "$VPS_HOST" > "$SCAN" 2>/dev/null || true
[[ -s "$SCAN" ]] || fail "Paris VPS не отвечает на SSH $VPS_HOST:$VPS_PORT"

HOST_ID="$VPS_HOST"
ssh-keygen -F "$HOST_ID" -f "$KNOWN" > "$OLD" 2>/dev/null || true
NEW_KEYS="$(awk '!/^#/ && NF>=3 {print $2" "$3}' "$SCAN" | sort -u)"
OLD_KEYS="$(awk '!/^#/ && NF>=3 {print $2" "$3}' "$OLD" | sort -u)"
MATCH=0
if [[ -n "$OLD_KEYS" ]]; then
  while IFS= read -r k; do
    [[ -n "$k" ]] && grep -qxF "$k" <<<"$NEW_KEYS" && MATCH=1 && break
  done <<< "$OLD_KEYS"
fi

if [[ -n "$OLD_KEYS" && "$MATCH" != "1" ]]; then
  echo
  echo "⚠️ SSH host key Paris VPS изменился. Новый fingerprint:"
  ssh-keygen -lf "$SCAN" -E sha256 | awk '{print "   "$2"  ("$4")"}' | sort -u
  echo
  printf 'Подтверждаешь замену ключа именно для Paris VPS? [y/N]: '
  read -r CONFIRM
  case "$CONFIRM" in
    y|Y|yes|YES|д|Д|да|ДА) ;;
    *) fail "замена SSH host key отменена" ;;
  esac
  BACKUP="$KNOWN.endlume-backup-$(date +%Y%m%d-%H%M%S)"
  cp "$KNOWN" "$BACKUP"
  ssh-keygen -R "$VPS_HOST" -f "$KNOWN" >/dev/null 2>&1 || true
  cat "$SCAN" >> "$KNOWN"
  chmod 600 "$KNOWN"
  echo "✅ Host key заменён. Backup: $BACKUP"
elif [[ -z "$OLD_KEYS" ]]; then
  cat "$SCAN" >> "$KNOWN"
  chmod 600 "$KNOWN"
  echo "✅ SSH host key добавлен"
else
  echo "✅ SSH host key совпадает"
fi

ssh-keygen -F "$HOST_ID" -f "$KNOWN" >/dev/null 2>&1 || fail "SSH host key не записался в known_hosts"

echo "1/8 Получаю проверенный основной VPS setup…"
gh api -H "Accept: application/vnd.github.raw+json" "/repos/$REPO/contents/$CORE_PATH?ref=$CORE_REF" > "$CORE" || fail "не удалось получить VPS setup core"
[[ -s "$CORE" ]] || fail "VPS setup core пуст"
chmod 755 "$CORE"
/bin/bash -n "$CORE" || fail "VPS setup core не прошёл bash syntax"
grep -Fq 'infra/vps-update/server.py' "$CORE" || fail "VPS server component отсутствует в core"
grep -Fq 'signer generate -w "$TAURI_KEY" --ci' "$CORE" || fail "Tauri signing setup отсутствует в core"

echo "✅ Paris VPS выбран автоматически"
echo "✅ root / port 22 выбраны автоматически"
echo "✅ Дальше может понадобиться только ОДИН ввод пароля VPS"
echo
printf '%s\n%s\n%s\n' "$VPS_HOST" "$VPS_USER" "$VPS_PORT" | /bin/bash "$CORE"

DEPLOY_KEY="$HOME/.endlume-updater/vps_deploy_ed25519"
if [[ -s "$DEPLOY_KEY" ]]; then
  echo
  echo "8/8 Закрываю временный root password SSH bootstrap…"
  ssh -i "$DEPLOY_KEY" -p "$VPS_PORT" -o BatchMode=yes -o StrictHostKeyChecking=yes "$VPS_USER@$VPS_HOST" \
    "if [ -f /etc/ssh/sshd_config.d/00-endlume-bootstrap.conf ]; then rm -f /etc/ssh/sshd_config.d/00-endlume-bootstrap.conf; /usr/sbin/sshd -t && systemctl restart ssh; fi" \
    || fail "ENDLUME настроен, но не удалось удалить временный SSH password bootstrap"
  echo "✅ Парольный root SSH снова закрыт; ENDLUME работает только по SSH key"
fi
