param([switch]$SkipAppleDriver, [switch]$SkipSystemInstall, [switch]$Start)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$taskRoot = $PSScriptRoot
if ([Environment]::OSVersion.Platform -ne 'Win32NT' -or ![Environment]::Is64BitOperatingSystem) { throw 'Windows x64 is required.' }
function Invoke-Checked {
    param([string]$File, [string[]]$Arguments)
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $File (exit $LASTEXITCODE)" }
}
function Install-WingetPackage {
    param([string]$Id)
    if (!(Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install Microsoft App Installer first: https://apps.microsoft.com/detail/9nblggh4nns1' }
    Invoke-Checked winget @('install','--id',$Id,'--exact','--source','winget','--accept-package-agreements','--accept-source-agreements','--disable-interactivity')
}
function Find-TaskPython {
    $taskCandidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:ProgramFiles 'Python313\python.exe')
    )
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $taskFound = & py -3.13 -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $taskFound) { $taskCandidates += [string]$taskFound }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) { $taskCandidates += (Get-Command python).Source }
    foreach ($taskCandidate in $taskCandidates) {
        if (!(Test-Path -LiteralPath $taskCandidate)) { continue }
        & $taskCandidate -c 'import sys,struct;sys.exit(0 if sys.version_info[:2]==(3,13) and struct.calcsize(chr(80))==8 else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return $taskCandidate }
    }
    return $null
}
$taskPython = Find-TaskPython
if (!$taskPython -and !$SkipSystemInstall) { Install-WingetPackage 'Python.Python.3.13'; $taskPython = Find-TaskPython }
if (!$taskPython) { throw 'Python 3.13 x64 is required. Install it, then rerun Install.ps1.' }
$taskNode = Join-Path $env:ProgramFiles 'nodejs\node.exe'
if (!(Test-Path -LiteralPath $taskNode) -and (Get-Command node -ErrorAction SilentlyContinue)) { $taskNode = (Get-Command node).Source }
if (!(Test-Path -LiteralPath $taskNode) -and !$SkipSystemInstall) { Install-WingetPackage 'OpenJS.NodeJS.LTS'; $taskNode = Join-Path $env:ProgramFiles 'nodejs\node.exe' }
if (!(Test-Path -LiteralPath $taskNode)) { throw 'Node.js 24 or newer is required.' }
Invoke-Checked $taskNode @('-e','if(parseInt(process.versions.node)<24)process.exit(1)')
$env:PATH = (Split-Path -Parent $taskNode) + ';' + $env:PATH
$taskDriver = Get-Service -Name 'Apple Mobile Device Service' -ErrorAction SilentlyContinue
if (!$taskDriver -and !$SkipAppleDriver -and !$SkipSystemInstall) { Install-WingetPackage 'Apple.iTunes' }
$taskVenv = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $taskVenv)) { Invoke-Checked $taskPython @('-m','venv',(Join-Path $taskRoot '.venv')) }
Invoke-Checked $taskVenv @('-c','import sys,struct;sys.exit(0 if sys.version_info[:2]==(3,13) and struct.calcsize(chr(80))==8 else 1)')
Invoke-Checked $taskVenv @('-m','pip','install','-r',(Join-Path $taskRoot 'requirements-windows.lock.txt'))
Invoke-Checked $taskVenv @('-m','pip','check')
Invoke-Checked $taskVenv @((Join-Path $taskRoot 'tools\environment_check.py'))
Write-Host 'Environment ready. Run Start.ps1 to launch the project. Driver installation may require a reboot.'
if ($Start) { & (Join-Path $taskRoot 'Start.ps1') }
