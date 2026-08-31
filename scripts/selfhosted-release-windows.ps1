$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
$Request = Get-Content 'updates/cloudflare/build-request.json' -Raw | ConvertFrom-Json
if (-not $Request.enabled) { throw 'release request disabled' }
$Builder = [IO.Path]::GetFileName([string]$Request.builder)
if ($Builder -ne [string]$Request.builder -or -not $Builder.StartsWith('BUILD_ENDLUME_') -or -not $Builder.EndsWith('.ps1')) { throw 'unsafe Windows builder' }
$Version = [string]$Request.version
$Notes = [string]$Request.notes
$Bucket = 'endlume-private-updates'
$Key = Join-Path $HOME '.endlume-updater\endlume.key'
$Art = Join-Path ($env:RUNNER_TEMP ?? $env:TEMP) ("endlume-release-{0}-win" -f ($env:GITHUB_RUN_ID ?? 'local'))
Remove-Item $Art -Recurse -Force -ErrorAction SilentlyContinue
New-Item $Art -ItemType Directory -Force | Out-Null
if (-not (Test-Path $Builder)) { throw "Builder missing: $Builder" }
if (-not (Test-Path $Key)) { throw "Updater signing key missing: $Key" }

$env:TAURI_SIGNING_PRIVATE_KEY = $Key
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ''
$env:ENDLUME_RELEASE_ARTIFACT_DIR = $Art
$env:ENDLUME_RELEASE_PLATFORM = 'windows-x86_64'
$env:ENDLUME_RELEASE_VERSION = $Version

& powershell -NoProfile -ExecutionPolicy Bypass -File $Builder
if ($LASTEXITCODE -ne 0) { throw "Builder failed with code $LASTEXITCODE" }

$Sig = Get-ChildItem $Art -Recurse -File | Where-Object { $_.Name -match '\.(exe|msi)\.sig$' } | Select-Object -First 1
if (-not $Sig) { throw "No Windows updater signature in $Art" }
$AssetPath = $Sig.FullName.Substring(0, $Sig.FullName.Length - 4)
if (-not (Test-Path $AssetPath)) { throw "Updater asset missing for $($Sig.FullName)" }
$Asset = Get-Item $AssetPath
$Signature = (Get-Content $Sig.FullName -Raw).Trim()
$ObjectKey = "releases/endlume/stable/windows-x86_64/$Version/$($Asset.Name)"

npx --yes wrangler@4 r2 object put "$Bucket/$ObjectKey" --file "$($Asset.FullName)" --remote
if ($LASTEXITCODE -ne 0) { throw 'R2 asset upload failed' }

$Manifest = Join-Path $Art 'windows-x86_64.json'
@{
  version = $Version
  notes = $Notes
  pub_date = [DateTime]::UtcNow.ToString('o')
  object_key = $ObjectKey
  signature = $Signature
} | ConvertTo-Json -Depth 4 | Set-Content $Manifest -Encoding UTF8
npx --yes wrangler@4 r2 object put "$Bucket/manifests/endlume/stable/windows-x86_64.json" --file "$Manifest" --remote
if ($LASTEXITCODE -ne 0) { throw 'R2 manifest upload failed' }
Write-Host "ENDLUME $Version Windows signed updater published to private R2"
