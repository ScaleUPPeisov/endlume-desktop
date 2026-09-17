$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location (Join-Path $PSScriptRoot '..')
$Target = 'x86_64-pc-windows-msvc'
$Version = (Get-Content 'package.json' -Raw | ConvertFrom-Json).version
$ExpectedVersion = '1.0.0-alpha.8.61'
if ($Version -ne $ExpectedVersion) { throw "Unexpected ENDLUME version: $Version" }

& (Join-Path $PSScriptRoot 'prepare-windows-sidecars.ps1')

npm ci
npm run check
npm run build
cargo check --manifest-path src-tauri\Cargo.toml --target $Target
cargo test --manifest-path src-tauri\Cargo.toml --target $Target
npm run tauri build -- --target $Target --bundles nsis

$NsisDir = "src-tauri\target\$Target\release\bundle\nsis"
$FinalName = "ENDLUME-YT-Studio-PEISOV-Setup-$Version-x64.exe"
$FinalPath = Join-Path $NsisDir $FinalName
$Candidates = @(Get-ChildItem -Path $NsisDir -Filter '*.exe' -File -ErrorAction Stop | Where-Object { $_.Name -ne $FinalName } | Sort-Object LastWriteTimeUtc -Descending)
if (-not $Candidates -or $Candidates.Count -lt 1) { if (Test-Path $FinalPath) { Write-Host "ENDLUME Windows 8.61 installer: $FinalPath"; exit 0 }; throw 'NSIS installer was not produced' }
$Nsis = $Candidates[0]
Copy-Item $Nsis.FullName $FinalPath -Force
if (-not (Test-Path $FinalPath)) { throw "Final installer rename failed: $FinalPath" }
Write-Host "ENDLUME Windows 8.61 installer: $FinalPath"
