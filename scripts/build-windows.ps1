$ErrorActionPreference='Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$Target='x86_64-pc-windows-msvc'
New-Item -ItemType Directory -Force src-tauri\binaries | Out-Null
foreach($b in @('ffmpeg','ffprobe')){
  $src="vendor\windows-x64\$b.exe"; $dst="src-tauri\binaries\$b-$Target.exe"
  if(!(Test-Path $src)){throw "Missing $src"}; Copy-Item $src $dst -Force
}
npm install
npm run tauri build -- --target $Target
