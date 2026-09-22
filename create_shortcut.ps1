param([Parameter(Mandatory=$true)][string]$InstallRoot)
$ErrorActionPreference = 'Stop'
$Shell = New-Object -ComObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath('Desktop')
$Shortcut = $Shell.CreateShortcut((Join-Path $DesktopPath 'Source Extractor.lnk'))
$Shortcut.TargetPath = Join-Path $InstallRoot '.venv\Scripts\pythonw.exe'
$Shortcut.Arguments = '"' + (Join-Path $InstallRoot 'desktop_launcher.py') + '"'
$Shortcut.WorkingDirectory = $InstallRoot
$Shortcut.Description = 'Source Extractor'
$Shortcut.Save()
