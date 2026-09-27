$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location (Join-Path $PSScriptRoot '..')

$Target = 'x86_64-pc-windows-msvc'
$ReleaseTag = 'autobuild-2026-09-14-13-17'
$ArchiveName = 'ffmpeg-N-126549-ga51bb69b09-win64-gpl.zip'
$Url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/$ReleaseTag/$ArchiveName"
$Cache = Join-Path $env:RUNNER_TEMP 'endlume-ffmpeg'
if (-not $env:RUNNER_TEMP) { $Cache = Join-Path $env:TEMP 'endlume-ffmpeg' }
$Zip = Join-Path $Cache $ArchiveName
$Extract = Join-Path $Cache 'extract'
$Dest = Join-Path (Get-Location) 'src-tauri\binaries'

New-Item -ItemType Directory -Force $Cache, $Dest | Out-Null
if (-not (Test-Path $Zip)) {
  Write-Host "Downloading pinned FFmpeg build $ReleaseTag"
  Invoke-WebRequest -Uri $Url -OutFile $Zip -UseBasicParsing
}
if (Test-Path $Extract) { Remove-Item $Extract -Recurse -Force }
Expand-Archive -Path $Zip -DestinationPath $Extract -Force

foreach ($Binary in @('ffmpeg','ffprobe')) {
  $Source = Get-ChildItem -Path $Extract -Recurse -File -Filter "$Binary.exe" | Select-Object -First 1
  if (-not $Source) { throw "Pinned archive does not contain $Binary.exe" }
  $Destination = Join-Path $Dest "$Binary-$Target.exe"
  Copy-Item $Source.FullName $Destination -Force
  if (-not (Test-Path $Destination)) { throw "Failed to stage $Destination" }
}

$Ffmpeg = Join-Path $Dest "ffmpeg-$Target.exe"
$Ffprobe = Join-Path $Dest "ffprobe-$Target.exe"
& $Ffmpeg -hide_banner -version | Select-Object -First 1
& $Ffprobe -hide_banner -version | Select-Object -First 1
$Encoders = (& $Ffmpeg -hide_banner -encoders 2>&1 | Out-String)
foreach ($Required in @('libx264','libx265','h264_nvenc','hevc_nvenc','h264_qsv','hevc_qsv','h264_amf','hevc_amf')) {
  if ($Encoders -notmatch [regex]::Escape($Required)) { throw "FFmpeg sidecar is missing encoder $Required" }
}
Write-Host 'Windows FFmpeg sidecars staged and capability list validated.'
