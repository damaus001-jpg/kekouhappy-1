param(
    [string]$Destination = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'qunkong-recovered'),
    [string]$Ref = 'master'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ([Environment]::OSVersion.Platform -ne 'Win32NT' -or ![Environment]::Is64BitOperatingSystem) {
    throw 'Disaster recovery requires Windows x64.'
}
$target = [IO.Path]::GetFullPath($Destination)
$resumeInstall = $false
if (Test-Path -LiteralPath $target) {
    $existingInstaller = Join-Path $target 'Install.ps1'
    $resumeInstall = (Test-Path -LiteralPath $existingInstaller) -and
        (Test-Path -LiteralPath (Join-Path $target 'VERSION')) -and
        (Test-Path -LiteralPath (Join-Path $target 'requirements-windows.lock.txt'))
    if (!$resumeInstall -and (Get-ChildItem -LiteralPath $target -Force | Measure-Object).Count -ne 0) {
        throw "Recovery destination must be empty; existing files were left untouched: $target"
    }
} elseif (!$resumeInstall) {
    New-Item -ItemType Directory -Path $target | Out-Null
}

$archive = $null
$extract = $null
if (!$resumeInstall) {
    $archive = Join-Path $env:TEMP ('qunkong-recovery-' + [guid]::NewGuid().ToString('N') + '.zip')
    $extract = Join-Path $env:TEMP ('qunkong-recovery-' + [guid]::NewGuid().ToString('N'))
    $refKind = if ($Ref -match '^v\d+\.\d+\.\d+$') { 'tags' } else { 'heads' }
    $uri = "https://github.com/damaus001-jpg/kekouhappy-1/archive/refs/$refKind/$Ref.zip"
    try {
        Invoke-WebRequest -Uri $uri -OutFile $archive
        Expand-Archive -LiteralPath $archive -DestinationPath $extract
        $root = Get-ChildItem -LiteralPath $extract -Directory | Select-Object -First 1
        if (!$root -or !(Test-Path -LiteralPath (Join-Path $root.FullName 'Install.ps1'))) {
            throw 'Downloaded project archive does not contain Install.ps1.'
        }
        Get-ChildItem -LiteralPath $root.FullName -Force | Copy-Item -Destination $target -Recurse -Force
    } finally {
        if ($archive) { Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue }
        if ($extract) { Remove-Item -LiteralPath $extract -Recurse -Force -ErrorAction SilentlyContinue }
    }
}
& (Join-Path $target 'Install.ps1') -Start
