param(
    [string[]]$Udid = @(),
    [ValidateRange(1024,65535)][int]$Port = 8070,
    [ValidateRange(1024,65535)][int]$BasePort = 8080
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskDashboard = Join-Path $PSScriptRoot 'dashboard.py'
$taskLogs = Join-Path $PSScriptRoot '.device-data\logs'
if (!(Test-Path -LiteralPath $taskPython)) { throw "Missing virtual environment: $taskPython" }
New-Item -ItemType Directory -Path $taskLogs -Force | Out-Null
$taskArguments = @(('"' + $taskDashboard + '"'), '--port', $Port, '--base-port', $BasePort)
foreach ($taskDevice in $Udid) {
    if ($taskDevice -notmatch '^[A-Za-z0-9-]+$') { throw 'Invalid UDID' }
    $taskArguments += @('--udid', $taskDevice)
}
$taskLaunch = Start-Process -FilePath $taskPython -ArgumentList $taskArguments -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskLogs "dashboard-$Port.out.log") -RedirectStandardError (Join-Path $taskLogs "dashboard-$Port.err.log") -PassThru
if ($taskLaunch.WaitForExit(2000)) {
    $taskError = Get-Content -LiteralPath (Join-Path $taskLogs "dashboard-$Port.err.log") -Raw
    throw "Dashboard exited with code $($taskLaunch.ExitCode): $taskError"
}
Write-Output "Started dashboard process $($taskLaunch.Id); http://127.0.0.1:$Port/"
