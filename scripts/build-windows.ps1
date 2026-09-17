$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location (Join-Path $PSScriptRoot '..')
$Target = 'x86_64-pc-windows-msvc'
$Version = (Get-Content 'package.json' -Raw | ConvertFrom-Json).version
$ExpectedVersion = '1.0.0-alpha.8.61'
if ($Version -ne $ExpectedVersion) { throw "Unexpected ENDLUME version: $Version" }

function Invoke-PythonGate {
    param([Parameter(Mandatory = $true)][string]$ScriptPath)
    $Python = Get-Command python -ErrorAction SilentlyContinue
    if ($Python) {
        & $Python.Source $ScriptPath
        if ($LASTEXITCODE -ne 0) { throw "Python gate failed: $ScriptPath" }
        return
    }
    $Py = Get-Command py -ErrorAction SilentlyContinue
    if ($Py) {
        & $Py.Source -3 $ScriptPath
        if ($LASTEXITCODE -ne 0) { throw "Python gate failed: $ScriptPath" }
        return
    }
    throw 'Python 3 is required on the Windows build runner for production regression gates'
}

& (Join-Path $PSScriptRoot 'prepare-windows-sidecars.ps1')

npm ci
npm run check
npm run build

Write-Host 'Running ENDLUME 8.61 Windows production contract gates...'
Invoke-PythonGate 'scripts/test-windows-861-strict-port.py'
Invoke-PythonGate 'scripts/test-windows-861-release-surface.py'
Invoke-PythonGate 'scripts/test-local-scratch-stability-8-61.py'
Invoke-PythonGate 'scripts/test-managed-license-render-gate.py'
Invoke-PythonGate 'scripts/test-render-speed-stability-8-60.py'

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
