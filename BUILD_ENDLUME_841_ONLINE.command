#!/bin/bash
set -Eeuo pipefail

# LaunchAgents start with a minimal PATH. Make the online release independent of
# Terminal shell profiles so Homebrew Node/gh and rustup/cargo are always found.
PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:/usr/local/bin:$HOME/.cargo/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PATH HOME COPYFILE_DISABLE=1 COPY_EXTENDED_ATTRIBUTES_DISABLE=1

command -v gh >/dev/null 2>&1 || { echo '8.41 online: gh missing' >&2; exit 1; }
command -v node >/dev/null 2>&1 || { echo '8.41 online: node missing' >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo '8.41 online: npm missing' >&2; exit 1; }
command -v npx >/dev/null 2>&1 || { echo '8.41 online: npx missing' >&2; exit 1; }
command -v cargo >/dev/null 2>&1 || { echo '8.41 online: cargo missing' >&2; exit 1; }
command -v rustup >/dev/null 2>&1 || { echo '8.41 online: rustup missing' >&2; exit 1; }

[[ -x /bin/bash ]] || exit 1
[[ -f BUILD_ENDLUME_841_GITHUB.command ]] || { echo '8.41 online: core builder missing' >&2; exit 1; }
/bin/bash -n BUILD_ENDLUME_841_GITHUB.command

echo "✅ 8.41 LaunchAgent toolchain PATH ready"
/bin/bash BUILD_ENDLUME_841_GITHUB.command
