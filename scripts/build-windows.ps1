$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location (Join-Path $PSScriptRoot '..')
$Target = 'x86_64-pc-windows-msvc'

& (Join-Path $PSScriptRoot 'prepare-windows-sidecars.ps1')

npm ci
npm run check
npm run build
cargo check --manifest-path src-tauri\Cargo.toml --target $Target
cargo test --manifest-path src-tauri\Cargo.toml --target $Target
npm run tauri build -- --target $Target --bundles nsis

$Nsis = Get-ChildItem -Path "src-tauri\target\$Target\release\bundle\nsis" -Filter '*-setup.exe' -File -ErrorAction Stop
if (-not $Nsis) { throw 'NSIS installer was not produced' }
Write-Host "ENDLUME Windows 8.61 installer: $($Nsis.FullName)"
