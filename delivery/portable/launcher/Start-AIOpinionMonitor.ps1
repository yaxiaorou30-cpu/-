[CmdletBinding()]
param(
    [switch]$NoBrowser,

    [ValidateRange(1, 65516)]
    [int]$BasePort = 8765,

    [ValidateRange(5, 120)]
    [int]$StartupTimeoutSeconds = 25,

    [string]$StateRoot = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ExpectedPythonSha256 = "30557F6B49FC4B6574CA3EF91EDB8D148CFC989DD75C846F5639B76DB800E7E2"
$ExpectedPythonwSha256 = "213191D5F0464D43E0D0963D3DF4E75AFA9909E33E49CA4FA2D24FF069432894"
$ExpectedVenvLauncherSha256 = "FF99D4C33C02F530D2A1FADADFA3C0175A616310F5895D72EAFD755E89D97E16"
$ProductRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$PrivatePythonRoot = Join-Path $ProductRoot ".runtime\python"
$PrivatePython = Join-Path $PrivatePythonRoot "python.exe"
$ServerPython = Join-Path $PrivatePythonRoot "pythonw.exe"
$RunnerPath = Join-Path $PSScriptRoot "Run-AIOpinionMonitor.py"
$MainSitePackages = Join-Path $ProductRoot ".venv\Lib\site-packages"
$AppPath = Join-Path $ProductRoot "web_app.py"
$BrowserRoot = Join-Path $ProductRoot ".runtime\browsers"

function Test-SamePath {
    param([string]$Left, [string]$Right)
    if ([string]::IsNullOrWhiteSpace($Left) -or [string]::IsNullOrWhiteSpace($Right)) {
        return $false
    }
    return [IO.Path]::GetFullPath($Left).Equals([IO.Path]::GetFullPath($Right), [StringComparison]::OrdinalIgnoreCase)
}

function Get-Sha256Hex {
    param([string]$Path)

    $Stream = [IO.File]::OpenRead($Path)
    $Hasher = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($Hasher.ComputeHash($Stream))).Replace("-", "")
    }
    finally {
        $Hasher.Dispose()
        $Stream.Dispose()
    }
}

function Test-ChildPath {
    param([string]$Path, [string]$Parent)

    if ([string]::IsNullOrWhiteSpace($Path) -or [string]::IsNullOrWhiteSpace($Parent)) {
        return $false
    }
    $ParentPrefix = [IO.Path]::GetFullPath($Parent).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    return [IO.Path]::GetFullPath($Path).StartsWith($ParentPrefix, [StringComparison]::OrdinalIgnoreCase)
}

function Get-LoopbackListenerProcessIds {
    param([int]$Port)

    $NetstatPath = Join-Path ([Environment]::SystemDirectory) "netstat.exe"
    foreach ($Line in & $NetstatPath -ano -p TCP) {
        $Parts = @($Line -split "\s+" | Where-Object { $_ })
        if ($Parts.Count -lt 5 -or $Parts[0] -ne "TCP" -or $Parts[1] -ne "127.0.0.1:$Port") {
            continue
        }
        $OwnerProcessId = 0
        if ([int]::TryParse($Parts[$Parts.Count - 1], [ref]$OwnerProcessId)) {
            $OwnerProcessId
        }
    }
}

function Stop-VerifiedStartedProcess {
    param(
        [Diagnostics.Process]$Process,
        [long]$ExpectedStartTimeUtcTicks,
        [string]$StopRequestPath,
        [string]$StopRequestToken
    )

    $CurrentProcess = Get-Process -Id $Process.Id -ErrorAction SilentlyContinue
    if ($null -eq $CurrentProcess) {
        return
    }
    if (
        -not (Test-SamePath $CurrentProcess.Path $ServerPython) -or
        $CurrentProcess.StartTime.ToUniversalTime().Ticks -ne $ExpectedStartTimeUtcTicks
    ) {
        throw "Started-process identity changed during cleanup. Refusing to stop an unverified process."
    }

    $GracefulRequestWritten = $false
    if (
        -not [string]::IsNullOrWhiteSpace($StopRequestPath) -and
        -not [string]::IsNullOrWhiteSpace($StopRequestToken)
    ) {
        try {
            [IO.File]::WriteAllText(
                $StopRequestPath,
                $StopRequestToken,
                [Text.UTF8Encoding]::new($false)
            )
            $GracefulRequestWritten = $true
        }
        catch {
        }
    }
    if ($GracefulRequestWritten -and $CurrentProcess.WaitForExit(15000)) {
        return
    }

    $CurrentProcess = Get-Process -Id $Process.Id -ErrorAction SilentlyContinue
    if ($null -eq $CurrentProcess) {
        return
    }
    if (
        -not (Test-SamePath $CurrentProcess.Path $ServerPython) -or
        $CurrentProcess.StartTime.ToUniversalTime().Ticks -ne $ExpectedStartTimeUtcTicks
    ) {
        throw "Started-process identity changed before forced cleanup. Refusing to stop an unverified process."
    }
    $TaskkillPath = Join-Path ([Environment]::SystemDirectory) "taskkill.exe"
    & $TaskkillPath /PID $CurrentProcess.Id /T /F > $null 2>&1
    $TaskkillExitCode = $LASTEXITCODE
    $CurrentProcess = Get-Process -Id $Process.Id -ErrorAction SilentlyContinue
    if ($TaskkillExitCode -ne 0 -and $null -ne $CurrentProcess) {
        throw "Forced process-tree cleanup failed with exit code $TaskkillExitCode."
    }
    if ($null -ne $CurrentProcess -and -not $CurrentProcess.WaitForExit(5000)) {
        throw "The verified process tree did not stop within 5 seconds."
    }
    if (Get-Process -Id $Process.Id -ErrorAction SilentlyContinue) {
        throw "The verified process tree is still running after forced cleanup."
    }
}

function Write-StateAtomically {
    param($State)

    $TemporaryStatePath = "$StatePath.$PID.$([Guid]::NewGuid().ToString('N')).tmp"
    try {
        [IO.File]::WriteAllText(
            $TemporaryStatePath,
            ($State | ConvertTo-Json -Depth 4),
            [Text.UTF8Encoding]::new($false)
        )
        if (Test-Path -LiteralPath $StatePath -PathType Container) {
            throw "The launcher state path is a directory."
        }
        Move-Item -LiteralPath $TemporaryStatePath -Destination $StatePath -Force
    }
    finally {
        Remove-Item -LiteralPath $TemporaryStatePath -Force -ErrorAction SilentlyContinue
    }
}

function Repair-VenvConfig {
    param([string]$VenvRoot)
    $ConfigPath = Join-Path $VenvRoot "pyvenv.cfg"
    $VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        throw "Missing private environment configuration: $ConfigPath"
    }
    if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        throw "Missing private environment interpreter: $VenvPython"
    }
    if ((Get-Sha256Hex $VenvPython) -ne $ExpectedVenvLauncherSha256) {
        throw "Private environment launcher integrity verification failed: $VenvPython"
    }
    $Lines = @(
        "home = $PrivatePythonRoot",
        "include-system-site-packages = false",
        "version = 3.13.9",
        "executable = $PrivatePython",
        "command = $PrivatePython -m venv --without-pip $VenvRoot"
    )
    [IO.File]::WriteAllText(
        $ConfigPath,
        ($Lines -join [Environment]::NewLine) + [Environment]::NewLine,
        [Text.UTF8Encoding]::new($false)
    )
}

function Get-StateDisposition {
    param($State)

    $RequiredProperties = @(
        "lifecycle",
        "processId",
        "processStartTimeUtcTicks",
        "port",
        "productRoot",
        "pythonPath",
        "stdoutLog",
        "stderrLog",
        "stopFile",
        "stopToken"
    )
    foreach ($PropertyName in $RequiredProperties) {
        if ($State.PSObject.Properties.Name -notcontains $PropertyName) {
            return "CORRUPT"
        }
    }

    try {
        $StateProcessId = [int]$State.processId
        $StateStartTimeUtcTicks = [long]$State.processStartTimeUtcTicks
        $StatePort = [int]$State.port
        $StatePythonPath = [string]$State.pythonPath
        $StateLifecycle = [string]$State.lifecycle
        if (
            $StateProcessId -le 0 -or
            $StateStartTimeUtcTicks -le 0 -or
            $StatePort -lt 1 -or
            $StatePort -gt 65535 -or
            $StateLifecycle -notin @("STARTING", "READY") -or
            -not (Test-ChildPath ([string]$State.stdoutLog) $StateBoundaryRoot) -or
            -not (Test-ChildPath ([string]$State.stderrLog) $StateBoundaryRoot) -or
            -not (Test-ChildPath ([string]$State.stopFile) $StateBoundaryRoot) -or
            ([string]$State.stopToken).Length -lt 32
        ) {
            return "CORRUPT"
        }
    }
    catch {
        return "CORRUPT"
    }

    $ServerProcess = Get-Process -Id $StateProcessId -ErrorAction SilentlyContinue
    if ($null -eq $ServerProcess) {
        return "STALE"
    }
    try {
        if (-not (Test-SamePath $ServerProcess.Path $StatePythonPath)) {
            return "STALE"
        }
        if ($ServerProcess.StartTime.ToUniversalTime().Ticks -ne $StateStartTimeUtcTicks) {
            return "STALE"
        }
        if (
            -not (Test-SamePath ([string]$State.productRoot) $ProductRoot) -or
            -not (Test-SamePath $StatePythonPath $ServerPython)
        ) {
            return "FOREIGN_RUNNING"
        }
        if ($StateLifecycle -eq "STARTING") {
            return "STARTING"
        }
        $HealthUri = "http://127.0.0.1:{0}/api/auth/status" -f $StatePort
        $HealthResponse = Invoke-WebRequest -UseBasicParsing -Uri $HealthUri -TimeoutSec 2
        if ($HealthResponse.StatusCode -ne 200) {
            return "UNHEALTHY"
        }
        $HealthPayload = $HealthResponse.Content | ConvertFrom-Json
        if ($HealthPayload.PSObject.Properties.Name -notcontains "ok" -or -not [bool]$HealthPayload.ok) {
            return "UNHEALTHY"
        }
        if ((@(Get-LoopbackListenerProcessIds $StatePort)) -notcontains $StateProcessId) {
            return "UNHEALTHY"
        }
        return "HEALTHY"
    }
    catch {
        return "UNVERIFIABLE"
    }
}

foreach ($RequiredPath in @($PrivatePython, $ServerPython, $RunnerPath, $MainSitePackages, $AppPath, $BrowserRoot)) {
    if (-not (Test-Path -LiteralPath $RequiredPath)) {
        throw "The software directory is incomplete. Missing: $RequiredPath"
    }
}
$ActualPythonSha256 = Get-Sha256Hex $PrivatePython
if ($ActualPythonSha256 -ne $ExpectedPythonSha256) {
    throw "Private Python integrity verification failed. Obtain a fresh software directory."
}
$ActualPythonwSha256 = Get-Sha256Hex $ServerPython
if ($ActualPythonwSha256 -ne $ExpectedPythonwSha256) {
    throw "Private Python windowed launcher integrity verification failed. Obtain a fresh software directory."
}
$DefaultAppDataRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "AI-Opinion-Monitor"
if ([string]::IsNullOrWhiteSpace($StateRoot)) {
    $ResolvedStateRoot = Join-Path $DefaultAppDataRoot "runtime"
    $StateBoundaryRoot = $DefaultAppDataRoot
    $LogRoot = Join-Path $DefaultAppDataRoot "logs"
    $SensitiveRoot = Join-Path $DefaultAppDataRoot "sensitive"
}
else {
    $ResolvedStateRoot = [IO.Path]::GetFullPath($StateRoot)
    $StateBoundaryRoot = $ResolvedStateRoot
    $TempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (-not $ResolvedStateRoot.StartsWith($TempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "A custom StateRoot is permitted only under the system temporary directory."
    }
    $LogRoot = Join-Path $ResolvedStateRoot "logs"
    $SensitiveRoot = Join-Path $ResolvedStateRoot "sensitive"
}
New-Item -ItemType Directory -Path $ResolvedStateRoot -Force | Out-Null
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
New-Item -ItemType Directory -Path $SensitiveRoot -Force | Out-Null

$LockPath = Join-Path $ResolvedStateRoot "launcher.lock"
$StatePath = Join-Path $ResolvedStateRoot "server-state.json"
$LockStream = $null
$ServerProcess = $null
$ServerProcessStartTimeUtcTicks = $null
$KeepServerProcess = $false
$OwnsState = $false
$StopFile = $null
$ChildEnvironmentNames = @(
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONUTF8",
    "PYTHONIOENCODING",
    "PYTHONNOUSERSITE",
    "PLAYWRIGHT_BROWSERS_PATH",
    "OPINION_SYSTEM_SENSITIVE_DIR",
    "AOM_LAUNCHER_STDOUT_LOG",
    "AOM_LAUNCHER_STDERR_LOG",
    "AOM_LAUNCHER_STOP_FILE",
    "AOM_LAUNCHER_STOP_TOKEN"
)
$SavedChildEnvironment = @{}
foreach ($Name in $ChildEnvironmentNames) {
    $Value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ($null -ne $Value) {
        $SavedChildEnvironment[$Name] = $Value
    }
}
try {
    try {
        $LockStream = [IO.File]::Open($LockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    }
    catch {
        throw "Another start or stop operation is in progress. Try again shortly."
    }

    $VenvRoots = @(
        (Join-Path $ProductRoot ".venv"),
        (Join-Path $ProductRoot ".scrapling-venv"),
        (Join-Path $ProductRoot "opensource_candidates\bilibili-cli\.venv"),
        (Join-Path $ProductRoot "opensource_candidates\newspaper4k\.venv"),
        (Join-Path $ProductRoot "opensource_candidates\aiotieba\.venv")
    )
    foreach ($VenvRoot in $VenvRoots) {
        Repair-VenvConfig $VenvRoot
    }

    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONNOUSERSITE = "1"
    Remove-Item -LiteralPath "Env:PYTHONHOME" -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath "Env:PYTHONPATH" -ErrorAction SilentlyContinue
    $env:PLAYWRIGHT_BROWSERS_PATH = $BrowserRoot
    $env:OPINION_SYSTEM_SENSITIVE_DIR = $SensitiveRoot

    if (Test-Path -LiteralPath $StatePath -PathType Leaf) {
        try {
            $ExistingState = Get-Content -Raw -Encoding UTF8 -LiteralPath $StatePath | ConvertFrom-Json
        }
        catch {
            throw "The existing launcher state is unreadable. It was preserved; see the user guide before retrying."
        }
        $StateDisposition = Get-StateDisposition $ExistingState
        switch ($StateDisposition) {
            "HEALTHY" {
                $ExistingUrl = "http://127.0.0.1:{0}" -f [int]$ExistingState.port
                if (-not $NoBrowser) {
                    Start-Process -FilePath $ExistingUrl
                }
                Write-Output "STATUS=ALREADY_RUNNING"
                Write-Output "URL=$ExistingUrl"
                Write-Output "PROCESS_ID=$($ExistingState.processId)"
                return
            }
            "STALE" {
                Remove-Item -LiteralPath $StatePath -Force
            }
            "FOREIGN_RUNNING" {
                throw "Another verified portable copy is already running. Stop that copy before starting this one."
            }
            "STARTING" {
                throw "The verified software process is still starting. Wait briefly or stop it before retrying."
            }
            "UNHEALTHY" {
                throw "The verified software process is running but not healthy. Stop it before retrying."
            }
            default {
                throw "The existing launcher state cannot be verified. It was preserved; see the user guide before retrying."
            }
        }
    }

    $ActivePorts = @(
        [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
            ForEach-Object { $_.Port }
    )
    $SelectedPort = $null
    foreach ($CandidatePort in $BasePort..($BasePort + 19)) {
        if ($CandidatePort -notin $ActivePorts) {
            $SelectedPort = $CandidatePort
            break
        }
    }
    if ($null -eq $SelectedPort) {
        throw "Ports $BasePort-$($BasePort + 19) are all in use. The software cannot start."
    }

    $LogId = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ") + "-" + [Guid]::NewGuid().ToString("N").Substring(0, 8)
    $StdoutLog = Join-Path $LogRoot "$LogId.stdout.log"
    $StderrLog = Join-Path $LogRoot "$LogId.stderr.log"
    $StopFile = Join-Path $ResolvedStateRoot "$LogId.stop.request"
    $StopToken = [Guid]::NewGuid().ToString("N")
    Remove-Item -LiteralPath $StopFile -Force -ErrorAction SilentlyContinue
    $env:AOM_LAUNCHER_STDOUT_LOG = $StdoutLog
    $env:AOM_LAUNCHER_STDERR_LOG = $StderrLog
    $env:AOM_LAUNCHER_STOP_FILE = $StopFile
    $env:AOM_LAUNCHER_STOP_TOKEN = $StopToken
    $Arguments = @(
        "-I",
        "-B",
        "-X",
        "utf8",
        ('"{0}"' -f $RunnerPath),
        "--host",
        "127.0.0.1",
        "--port",
        [string]$SelectedPort,
        "--no-browser"
    )
    $StartParameters = @{
        FilePath = $ServerPython
        ArgumentList = $Arguments
        WorkingDirectory = $ProductRoot
        WindowStyle = "Hidden"
        PassThru = $true
    }
    $ServerProcess = Start-Process @StartParameters
    $ServerProcessStartTimeUtcTicks = $ServerProcess.StartTime.ToUniversalTime().Ticks

    $State = [ordered]@{
        schemaVersion = 1
        lifecycle = "STARTING"
        processId = $ServerProcess.Id
        processStartTimeUtcTicks = $ServerProcessStartTimeUtcTicks
        port = $SelectedPort
        productRoot = $ProductRoot
        pythonPath = $ServerPython
        startedAtUtc = [DateTime]::UtcNow.ToString("o")
        stdoutLog = $StdoutLog
        stderrLog = $StderrLog
        stopFile = $StopFile
        stopToken = $StopToken
    }
    try {
        Write-StateAtomically $State
        $OwnsState = $true
    }
    catch {
        throw "Failed to persist STARTING launcher state: $($_.Exception.Message)"
    }

    $HealthUri = "http://127.0.0.1:$SelectedPort/api/auth/status"
    $Ready = $false
    $Deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
    while ([DateTime]::UtcNow -lt $Deadline) {
        if ($ServerProcess.HasExited) {
            break
        }
        try {
            $HealthResponse = Invoke-WebRequest -UseBasicParsing -Uri $HealthUri -TimeoutSec 1
            if ($HealthResponse.StatusCode -eq 200) {
                $HealthPayload = $HealthResponse.Content | ConvertFrom-Json
                if (
                    $HealthPayload.PSObject.Properties.Name -contains "ok" -and
                    [bool]$HealthPayload.ok -and
                    (@(Get-LoopbackListenerProcessIds $SelectedPort)) -contains $ServerProcess.Id
                ) {
                    $Ready = $true
                    break
                }
            }
        }
        catch {
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $Ready) {
        throw "The software failed to start. See the log: $StderrLog"
    }

    $State["lifecycle"] = "READY"
    $State["readyAtUtc"] = [DateTime]::UtcNow.ToString("o")
    Write-StateAtomically $State
    $KeepServerProcess = $true

    $AppUrl = "http://127.0.0.1:$SelectedPort"
    if (-not $NoBrowser) {
        Start-Process -FilePath $AppUrl
    }
    Write-Output "STATUS=STARTED"
    Write-Output "URL=$AppUrl"
    Write-Output "PROCESS_ID=$($ServerProcess.Id)"
    Write-Output "LIFECYCLE=READY"
}
finally {
    $CleanupCompleted = $null -eq $ServerProcess
    $CleanupFailure = $null
    if (-not $KeepServerProcess -and $null -ne $ServerProcess) {
        try {
            Stop-VerifiedStartedProcess `
                -Process $ServerProcess `
                -ExpectedStartTimeUtcTicks $ServerProcessStartTimeUtcTicks `
                -StopRequestPath $StopFile `
                -StopRequestToken $StopToken
            $CleanupCompleted = $true
        }
        catch {
            $CleanupFailure = $_.Exception
        }
    }
    if (
        -not $KeepServerProcess -and
        $CleanupCompleted -and
        $OwnsState -and
        (Test-Path -LiteralPath $StatePath -PathType Leaf)
    ) {
        try {
            $FailedState = Get-Content -Raw -Encoding UTF8 -LiteralPath $StatePath | ConvertFrom-Json
            if (
                [int]$FailedState.processId -eq $ServerProcess.Id -and
                [long]$FailedState.processStartTimeUtcTicks -eq $ServerProcessStartTimeUtcTicks -and
                (Test-SamePath ([string]$FailedState.productRoot) $ProductRoot) -and
                (Test-SamePath ([string]$FailedState.pythonPath) $ServerPython)
            ) {
                Remove-Item -LiteralPath $StatePath -Force
            }
        }
        catch {
            if ($null -eq $CleanupFailure) {
                $CleanupFailure = $_.Exception
            }
        }
    }
    if (-not $KeepServerProcess -and $CleanupCompleted -and $null -ne $StopFile) {
        Remove-Item -LiteralPath $StopFile -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $LockStream) {
        $LockStream.Dispose()
    }
    foreach ($Name in $ChildEnvironmentNames) {
        if ($SavedChildEnvironment.ContainsKey($Name)) {
            Set-Item -LiteralPath "Env:$Name" -Value $SavedChildEnvironment[$Name]
        }
        else {
            Remove-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue
        }
    }
    if ($null -ne $CleanupFailure) {
        throw "The software failed to clean up its verified startup process: $($CleanupFailure.Message)"
    }
}
