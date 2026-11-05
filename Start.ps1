$ErrorActionPreference = 'Stop'
$taskNodeFolder = Join-Path $env:ProgramFiles 'nodejs'
if (Test-Path -LiteralPath $taskNodeFolder) { $env:PATH = $taskNodeFolder + ';' + $env:PATH }
& (Join-Path $PSScriptRoot 'iphone_batch\start_workspace.ps1')
Write-Output '请在授权客户端的“苹果”入口打开短信工作台。'
