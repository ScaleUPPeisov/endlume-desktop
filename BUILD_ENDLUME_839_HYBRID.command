#!/bin/bash
set -Eeuo pipefail
REPO="ScaleUPPeisov/endlume-desktop"
BRANCH="release"
BUILDER_NAME="BUILD_ENDLUME_839_LOCAL.command"
TMP="$(mktemp -d /tmp/endlume-839-hybrid.XXXXXX)"
BUILDER="$TMP/$BUILDER_NAME"
cleanup(){ rm -rf "$TMP" >/dev/null 2>&1 || true; }
trap cleanup EXIT
fail(){ echo; echo "❌ ENDLUME 8.39 HYBRID: $1"; exit 1; }

echo "@@ENDLUME_STAGE|Hybrid Update Center: получаю канонический 8.39 installer"
echo "@@ENDLUME_PROGRESS|2"
[[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon Mac"
command -v gh >/dev/null 2>&1 || fail "GitHub CLI не найден"
gh auth status -h github.com >/dev/null 2>&1 || fail "GitHub CLI не авторизован"

gh api "repos/$REPO/contents/$BUILDER_NAME?ref=$BRANCH" --jq .content | tr -d '\n' | /usr/bin/base64 -D > "$BUILDER" || fail "не удалось получить canonical local builder"
[[ -s "$BUILDER" ]] || fail "canonical local builder пуст"
chmod +x "$BUILDER"
/bin/bash -n "$BUILDER" || fail "canonical local builder syntax failed"
grep -Fq 'stage "10/10 Устанавливаю обновление" 96' "$BUILDER" || fail "stage10 safety preflight missing"
grep -Fq 'apply-hybrid-updater-8-39.py' "$BUILDER" || fail "Hybrid Update Center patch missing"
grep -Fq 'validate-release-8-39.sh' "$BUILDER" || fail "8.39 acceptance gate missing"
if grep -Fq 'ENDLUME_CI_ARTIFACT_DIR' "$BUILDER"; then fail "получен CI builder вместо local installer"; fi

echo "✅ 8.39 bridge FIXED: CI stage10 patching полностью удалён"
echo "✅ Канонический local installer содержит настоящий stage 10"
echo "@@ENDLUME_STAGE|Запускаю проверенную сборку 8.39"
echo "@@ENDLUME_PROGRESS|3"
ENDLUME_IN_APP_UPDATE=1 /bin/bash "$BUILDER"
