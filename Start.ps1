$ErrorActionPreference = 'Stop'
$taskNodeFolder = Join-Path $env:ProgramFiles 'nodejs'
if (Test-Path -LiteralPath $taskNodeFolder) { $env:PATH = $taskNodeFolder + ';' + $env:PATH }
& (Join-Path $PSScriptRoot 'iphone_batch\start_workspace.ps1')
Start-Process 'http://127.0.0.1:8070/'
