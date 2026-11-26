$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path $root 'Open Meridian Desk.lnk'))
$link.TargetPath = Join-Path $root 'runtime\python\pythonw.exe'
$link.Arguments = '-B "' + (Join-Path $root 'launch.py') + '"'
$link.WorkingDirectory = $root
$link.IconLocation = (Join-Path $root 'app\meridian.ico') + ',0'
$link.Description = 'Open the Meridian Desk trading and risk workstation'
$link.Save()