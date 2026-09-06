[CmdletBinding()]
param(
    [string]$StateRoot = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProductRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$ServerPython = Join-Path $ProductRoot ".runtime\python\pythonw.exe"

function Test-SamePath {
    param([string]$Left, [string]$Right)
    if ([string]::IsNullOrWhiteSpace($Left) -or [string]::IsNullOrWhiteSpace($Right)) {
        return $false
    }
    return [IO.Path]::GetFullPath($Left).Equals([IO.Path]::GetFullPath($Right), [StringComparison]::OrdinalIgnoreCase)
}

function Test-ChildPath {
    param([string]$Path, [string]$Parent)

    if ([string]::IsNullOrWhiteSpace($Path) -or [string]::IsNullOrWhiteSpace($Parent)) {
        return $false
    }
    $ParentPrefix = [IO.Path]::GetFullPath($Parent).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    return [IO.Path]::GetFullPath($Path).StartsWith($ParentPrefix, [StringComparison]::OrdinalIgnoreCase)
}

function Get-VerifiedStopRequestPath {
    param([string]$Path, [string]$ExpectedRoot)

    try {
        if ([string]::IsNullOrWhiteSpace($Path)) {
            throw "The stop request path is empty."
        }
        $FullPath = [IO.Path]::GetFullPath($Path)
        $Parent = [IO.Path]::GetDirectoryName($FullPath)
        $Name = [IO.Path]::GetFileName($FullPath)
        if (
            -not (Test-SamePath $Parent $ExpectedRoot) -or
            $Name -cnotmatch '^\d{8}T\d{6}Z-[0-9a-f]{8}\.stop\.request$'
        ) {
            throw "The stop request path is outside the runtime root or has an invalid name."
        }
        return $FullPath
    }
    catch {
        throw "The launcher state contains an unsafe path or value. Refusing to stop an unverified process."
    }
}

function Assert-VerifiedServerProcess {
    param(
        [Diagnostics.Process]$Process,
        [string]$ExpectedPythonPath,
        [long]$ExpectedStartTimeUtcTicks
    )

    try {
        if (
            $null -eq $Process -or
            -not (Test-SamePath $Process.Path $ExpectedPythonPath) -or
            $Process.StartTime.ToUniversalTime().Ticks -ne $ExpectedStartTimeUtcTicks
        ) {
            throw "Process identity mismatch."
        }
    }
    catch {
        throw "PID verification failed. Refusing to stop an unverified process."
    }
}

if ([string]::IsNullOrWhiteSpace($StateRoot)) {
    $StateBoundaryRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "AI-Opinion-Monitor"
    $ResolvedStateRoot = Join-Path $StateBoundaryRoot "runtime"
}
else {
    $ResolvedStateRoot = [IO.Path]::GetFullPath($StateRoot)
    $StateBoundaryRoot = $ResolvedStateRoot
    $TempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (-not $ResolvedStateRoot.StartsWith($TempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "A custom StateRoot is permitted only under the system temporary directory."
    }
}
$StatePath = Join-Path $ResolvedStateRoot "server-state.json"
New-Item -ItemType Directory -Path $ResolvedStateRoot -Force | Out-Null
$LockPath = Join-Path $ResolvedStateRoot "launcher.lock"
$LockStream = $null
try {
    try {
        $LockStream = [IO.File]::Open($LockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    }
    catch {
        throw "Another start or stop operation is in progress. Try again shortly."
    }

    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
        Write-Output "STATUS=NOT_RUNNING"
        return
    }

    $State = Get-Content -Raw -Encoding UTF8 -LiteralPath $StatePath | ConvertFrom-Json
    $RequiredProperties = @(
        "lifecycle",
        "processId",
        "processStartTimeUtcTicks",
        "productRoot",
        "pythonPath",
        "stdoutLog",
        "stderrLog",
        "stopFile",
        "stopToken"
    )
    foreach ($PropertyName in $RequiredProperties) {
        if ($State.PSObject.Properties.Name -notcontains $PropertyName) {
            throw "The launcher state is incomplete. Refusing to stop an unverified process."
        }
    }
    if (
        ([string]$State.lifecycle) -notin @("STARTING", "READY") -or
        -not (Test-ChildPath ([string]$State.stdoutLog) $StateBoundaryRoot) -or
        -not (Test-ChildPath ([string]$State.stderrLog) $StateBoundaryRoot) -or
        ([string]$State.stopToken).Length -lt 32
    ) {
        throw "The launcher state contains an unsafe path or value. Refusing to stop an unverified process."
    }
    $VerifiedStopFile = Get-VerifiedStopRequestPath `
        -Path ([string]$State.stopFile) `
        -ExpectedRoot $ResolvedStateRoot
    if (
        -not (Test-SamePath ([string]$State.productRoot) $ProductRoot) -or
        -not (Test-SamePath ([string]$State.pythonPath) $ServerPython)
    ) {
        throw "The state file does not belong to this software directory. Refusing to stop a process."
    }

    $ServerProcess = Get-Process -Id ([int]$State.processId) -ErrorAction SilentlyContinue
    if ($null -eq $ServerProcess) {
        $VerifiedStopFile = Get-VerifiedStopRequestPath `
            -Path ([string]$State.stopFile) `
            -ExpectedRoot $ResolvedStateRoot
        Remove-Item -LiteralPath $VerifiedStopFile -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $StatePath -Force
        Write-Output "STATUS=NOT_RUNNING"
        return
    }
    $ExpectedStartTimeUtcTicks = [long]$State.processStartTimeUtcTicks
    Assert-VerifiedServerProcess `
        -Process $ServerProcess `
        -ExpectedPythonPath $ServerPython `
        -ExpectedStartTimeUtcTicks $ExpectedStartTimeUtcTicks

    $VerifiedStopFile = Get-VerifiedStopRequestPath `
        -Path ([string]$State.stopFile) `
        -ExpectedRoot $ResolvedStateRoot
    [IO.File]::WriteAllText(
        $VerifiedStopFile,
        [string]$State.stopToken,
        [Text.UTF8Encoding]::new($false)
    )
    $StopMode = "GRACEFUL"
    if (-not $ServerProcess.WaitForExit(15000)) {
        $ForcedProcess = Get-Process -Id $ServerProcess.Id -ErrorAction SilentlyContinue
        if ($null -eq $ForcedProcess) {
            if (-not $ServerProcess.WaitForExit(0)) {
                throw "The verified software process exit could not be confirmed."
            }
        }
        else {
            Assert-VerifiedServerProcess `
                -Process $ForcedProcess `
                -ExpectedPythonPath $ServerPython `
                -ExpectedStartTimeUtcTicks $ExpectedStartTimeUtcTicks
            if (-not $ServerProcess.WaitForExit(0)) {
                $StopMode = "FORCED_TREE"
                $TaskkillPath = Join-Path ([Environment]::SystemDirectory) "taskkill.exe"
                & $TaskkillPath /PID $ForcedProcess.Id /T /F > $null 2>&1
                $TaskkillExitCode = $LASTEXITCODE
                if ($TaskkillExitCode -ne 0) {
                    throw "Forced process-tree cleanup failed with exit code $TaskkillExitCode."
                }
                if (-not $ServerProcess.WaitForExit(5000)) {
                    throw "The verified software process tree did not stop within 20 seconds."
                }
            }
        }
    }
    $VerifiedStopFile = Get-VerifiedStopRequestPath `
        -Path ([string]$State.stopFile) `
        -ExpectedRoot $ResolvedStateRoot
    Remove-Item -LiteralPath $VerifiedStopFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $StatePath -Force
    Write-Output "STATUS=STOPPED"
    Write-Output "PROCESS_ID=$($ServerProcess.Id)"
    Write-Output "STOP_MODE=$StopMode"
}
finally {
    if ($null -ne $LockStream) {
        $LockStream.Dispose()
    }
}
