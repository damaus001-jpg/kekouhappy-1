param([Parameter(Mandatory=$true)][int]$DashboardId)
$ErrorActionPreference = 'Stop'
$taskProcesses = @(Get-CimInstance Win32_Process)
$taskDashboard = $taskProcesses | Where-Object { $_.ProcessId -eq $DashboardId }
if (!$taskDashboard -or $taskDashboard.CommandLine -notmatch 'D:\\qunkong\\iphone_batch\\dashboard\.py') {
    throw 'Dashboard identity changed; restart cancelled.'
}
if ($taskProcesses | Where-Object { $_.Name -match '^python' -and $_.CommandLine -match 'native_workspace\.py|message_backup\.py' }) {
    throw 'Phone operation running; restart cancelled.'
}
$taskIds = @($DashboardId)
do {
    $taskMore = @($taskProcesses | Where-Object { $_.ParentProcessId -in $taskIds -and $_.ProcessId -notin $taskIds })
    $taskIds += @($taskMore | ForEach-Object { $_.ProcessId })
} while ($taskMore.Count -gt 0)
$taskPython = @($taskProcesses | Where-Object { $_.ProcessId -in $taskIds -and $_.Name -match '^python' })
foreach ($taskProcess in $taskPython) {
    if ($taskProcess.CommandLine -notmatch 'D:\\qunkong\\iphone_batch\\(dashboard|controller|pmd_entry)\.py') {
        throw 'Unexpected child process; restart cancelled.'
    }
}
Stop-Process -Id $DashboardId -Force
foreach ($taskProcess in $taskPython) {
    if ($taskProcess.ProcessId -ne $DashboardId) {
        Stop-Process -Id $taskProcess.ProcessId -Force -ErrorAction SilentlyContinue
    }
}
$taskLaunch = Start-Process -FilePath 'D:\qunkong\.venv\Scripts\python.exe' -ArgumentList @('D:\qunkong\iphone_batch\dashboard.py', '--udid', '00008030-001119CE0A93402E') -WorkingDirectory 'D:\qunkong' -WindowStyle Hidden -RedirectStandardOutput 'D:\qunkong\iphone_batch\.device-data\logs\incremental-dashboard.out.log' -RedirectStandardError 'D:\qunkong\iphone_batch\.device-data\logs\incremental-dashboard.err.log' -PassThru
Write-Output "Started dashboard process $($taskLaunch.Id)"
