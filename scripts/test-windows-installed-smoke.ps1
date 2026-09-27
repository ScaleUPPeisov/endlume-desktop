param(
  [Parameter(Mandatory = $true)][string]$Installer,
  [string]$ProductName = 'ENDLUME YT Studio PEISOV',
  [string]$ExpectedVersion = '1.0.0-alpha.8.61'
)

$ErrorActionPreference = 'Stop'
$Installer = (Resolve-Path -LiteralPath $Installer).Path
$StartMenuLink = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\$ProductName\$ProductName.lnk"
$DesktopLink = Join-Path ([Environment]::GetFolderPath('Desktop')) "$ProductName.lnk"

Add-Type @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class EndlumeVisibleWindows {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
  public static uint[] ProcessIds() {
    var ids = new HashSet<uint>();
    EnumWindows((hWnd, lParam) => {
      if (IsWindowVisible(hWnd)) { uint pid; GetWindowThreadProcessId(hWnd, out pid); if (pid != 0) ids.Add(pid); }
      return true;
    }, IntPtr.Zero);
    var result = new uint[ids.Count]; ids.CopyTo(result); return result;
  }
}
'@

function Get-UninstallEntry {
  $roots = @(
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
    'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
  )
  foreach ($root in $roots) {
    $entry = Get-ItemProperty $root -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -eq $ProductName } | Select-Object -First 1
    if ($entry) { return $entry }
  }
  return $null
}

function Wait-Until([scriptblock]$Condition, [int]$Seconds = 30, [string]$Failure = 'condition timeout') {
  $deadline = (Get-Date).AddSeconds($Seconds)
  do {
    if (& $Condition) { return }
    Start-Sleep -Milliseconds 300
  } while ((Get-Date) -lt $deadline)
  throw $Failure
}

function Resolve-ShortcutTarget([string]$Path) {
  if (!(Test-Path -LiteralPath $Path)) { throw "Shortcut missing: $Path" }
  $shell = New-Object -ComObject WScript.Shell
  return $shell.CreateShortcut($Path).TargetPath
}

function Get-InstallExe {
  $target = Resolve-ShortcutTarget $StartMenuLink
  if (!(Test-Path -LiteralPath $target)) { throw "Installed executable missing: $target" }
  return (Resolve-Path -LiteralPath $target).Path
}

function Uninstall-Current {
  $entry = Get-UninstallEntry
  if (-not $entry) { return }
  $uninstall = [string]$entry.UninstallString
  $exe = $null
  if ($uninstall -match '^\s*"([^"]+\.exe)"') { $exe = $Matches[1] }
  elseif ($uninstall -match '^\s*([^\s]+\.exe)') { $exe = $Matches[1] }
  if (-not $exe -or !(Test-Path -LiteralPath $exe)) { throw "Cannot resolve uninstaller from: $uninstall" }
  $p = Start-Process -FilePath $exe -ArgumentList '/S' -Wait -PassThru -WindowStyle Hidden
  if ($p.ExitCode -ne 0) { throw "Uninstaller failed: $($p.ExitCode)" }
  Wait-Until { -not (Get-UninstallEntry) } 30 'Product still registered after uninstall'
}

function Install-Current {
  $p = Start-Process -FilePath $Installer -ArgumentList '/S' -Wait -PassThru -WindowStyle Hidden
  if ($p.ExitCode -ne 0) { throw "Installer failed: $($p.ExitCode)" }
  Wait-Until { Get-UninstallEntry } 30 'Product did not register after install'
  Wait-Until { (Test-Path -LiteralPath $StartMenuLink) -and (Test-Path -LiteralPath $DesktopLink) } 30 'Required shortcuts were not created'
}

function Get-VisibleBlockedProcesses {
  $blocked = @('cmd','powershell','pwsh','windowsterminal','conhost','openconsole','ffmpeg','ffprobe')
  $result = @{}
  foreach ($pidValue in [EndlumeVisibleWindows]::ProcessIds()) {
    try {
      $p = Get-Process -Id $pidValue -ErrorAction Stop
      if ($blocked -contains $p.ProcessName.ToLowerInvariant()) { $result[[int]$p.Id] = $p.ProcessName }
    } catch {}
  }
  return $result
}

function Assert-InstalledSurface {
  $entry = Get-UninstallEntry
  if (-not $entry) { throw 'Apps & Features registration missing' }
  if ([string]$entry.DisplayName -ne $ProductName) { throw "Wrong DisplayName: $($entry.DisplayName)" }
  if ([string]$entry.DisplayVersion -ne $ExpectedVersion) { throw "Wrong DisplayVersion: $($entry.DisplayVersion)" }
  if ([string]$entry.Publisher -ne 'PEISOV') { throw "Wrong Publisher: $($entry.Publisher)" }

  $exe = Get-InstallExe
  $desktopTarget = Resolve-ShortcutTarget $DesktopLink
  if ((Resolve-Path -LiteralPath $desktopTarget).Path -ne $exe) { throw 'Desktop shortcut points to the wrong executable' }

  $vi = (Get-Item -LiteralPath $exe).VersionInfo
  if ($vi.ProductName -and $vi.ProductName -ne $ProductName) { throw "Wrong EXE ProductName: $($vi.ProductName)" }

  $dir = Split-Path -Parent $exe
  $ffmpeg = Get-ChildItem -LiteralPath $dir -Recurse -File -Filter 'ffmpeg*.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
  $ffprobe = Get-ChildItem -LiteralPath $dir -Recurse -File -Filter 'ffprobe*.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $ffmpeg) { throw 'Installed ffmpeg sidecar missing' }
  if (-not $ffprobe) { throw 'Installed ffprobe sidecar missing' }

  $baseline = Get-VisibleBlockedProcesses
  $app = Start-Process -FilePath $exe -PassThru
  try {
    Wait-Until { -not $app.HasExited } 8 'Application exited during launch'
    $deadline = (Get-Date).AddSeconds(10)
    do {
      $now = Get-VisibleBlockedProcesses
      foreach ($id in $now.Keys) {
        if (-not $baseline.ContainsKey($id)) { throw "Visible console/helper window detected during launch: $($now[$id]) pid=$id" }
      }
      Start-Sleep -Milliseconds 100
    } while ((Get-Date) -lt $deadline)
  } finally {
    if (-not $app.HasExited) { Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue }
  }

  Write-Host "ENDLUME_WINDOWS_INSTALLED_SURFACE_GREEN=$exe"
  Write-Host "ENDLUME_WINDOWS_INSTALLED_FFMPEG=$($ffmpeg.FullName)"
  Write-Host "ENDLUME_WINDOWS_INSTALLED_FFPROBE=$($ffprobe.FullName)"
}

# Persistent self-hosted runner hygiene + clean install -> uninstall -> reinstall verification.
Uninstall-Current
Install-Current
Assert-InstalledSurface
Uninstall-Current
Install-Current
Assert-InstalledSurface
Uninstall-Current
Write-Host 'ENDLUME_WINDOWS_INSTALL_UNINSTALL_REINSTALL_GREEN=1'
