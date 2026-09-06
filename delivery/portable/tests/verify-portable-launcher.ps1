[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$ProductRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) {
        throw $Message
    }
}

function Test-SamePath {
    param([string]$Left, [string]$Right)

    if ([string]::IsNullOrWhiteSpace($Left) -or [string]::IsNullOrWhiteSpace($Right)) {
        return $false
    }
    try {
        return [IO.Path]::GetFullPath($Left).Equals([IO.Path]::GetFullPath($Right), [StringComparison]::OrdinalIgnoreCase)
    }
    catch {
        return $false
    }
}

function Test-ProcessIdentity {
    param(
        [Diagnostics.Process]$Process,
        [string]$ExpectedPath,
        [long]$ExpectedStartTimeUtcTicks
    )

    if ($null -eq $Process) {
        return $false
    }
    try {
        return (
            (Test-SamePath $Process.Path $ExpectedPath) -and
            $Process.StartTime.ToUniversalTime().Ticks -eq $ExpectedStartTimeUtcTicks
        )
    }
    catch {
        return $false
    }
}

function Invoke-UserCommand {
    param(
        [string]$Path,
        [string[]]$Arguments,
        [string]$CleanupScript = "",
        [string]$CleanupStateRoot = ""
    )

    $CommandProcess = Start-Process -FilePath $Path -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    $CommandProcessPath = $CommandProcess.Path
    $CommandProcessStartTimeUtcTicks = $CommandProcess.StartTime.ToUniversalTime().Ticks
    if (-not $CommandProcess.WaitForExit(30000)) {
        try {
            $TimedOutProcess = Get-Process -Id $CommandProcess.Id -ErrorAction SilentlyContinue
            if ($null -eq $TimedOutProcess) {
                if (-not $CommandProcess.WaitForExit(0)) {
                    throw "The timed-out command process exit could not be confirmed."
                }
            }
            else {
                if (
                    -not (Test-ProcessIdentity `
                        -Process $TimedOutProcess `
                        -ExpectedPath $CommandProcessPath `
                        -ExpectedStartTimeUtcTicks $CommandProcessStartTimeUtcTicks)
                ) {
                    throw "The timed-out command PID identity changed. Refusing process-tree cleanup."
                }
                if (-not $CommandProcess.WaitForExit(0)) {
                    $TaskkillPath = Join-Path ([Environment]::SystemDirectory) "taskkill.exe"
                    & $TaskkillPath /PID $TimedOutProcess.Id /T /F > $null 2>&1
                    $TaskkillExitCode = $LASTEXITCODE
                    if ($TaskkillExitCode -ne 0) {
                        throw "Timed-out command cleanup failed with exit code $TaskkillExitCode."
                    }
                    if (-not $CommandProcess.WaitForExit(5000)) {
                        throw "The timed-out command process-tree exit could not be confirmed."
                    }
                }
            }
        }
        finally {
            if ($CleanupScript -and $CleanupStateRoot) {
                try { & $CleanupScript -StateRoot $CleanupStateRoot | Out-Null } catch { }
            }
        }
        throw "The user-facing command did not exit within 30 seconds: $Path"
    }
    if ($CommandProcess.ExitCode -ne 0) {
        if ($CleanupScript -and $CleanupStateRoot) {
            try { & $CleanupScript -StateRoot $CleanupStateRoot | Out-Null } catch { }
        }
        throw "The user-facing command failed with exit code $($CommandProcess.ExitCode): $Path"
    }
}

function Test-ChildPath {
    param([string]$Path, [string]$Parent)

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

function Assert-EnvironmentMatches {
    param(
        [hashtable]$Expected,
        [string[]]$Names,
        [string]$Context
    )

    foreach ($Name in $Names) {
        $ExpectedValue = $Expected[$Name]
        $ActualValue = [Environment]::GetEnvironmentVariable($Name, "Process")
        Assert-True ($ActualValue -eq $ExpectedValue) "$Context environment variable mismatch: $Name"
    }
}

Assert-True (
    $PSVersionTable.PSEdition -eq "Desktop" -and
    $PSVersionTable.PSVersion.Major -eq 5 -and
    $PSVersionTable.PSVersion.Minor -eq 1
) "This acceptance test must run in Windows PowerShell 5.1."

$LauncherSource = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\launcher"))
$StartCmdName = (-join @([char]0x542F, [char]0x52A8, [char]0x8F6F, [char]0x4EF6)) + ".cmd"
$StopCmdName = (-join @([char]0x505C, [char]0x6B62, [char]0x8F6F, [char]0x4EF6)) + ".cmd"
$ExpectedAssets = @(
    "Start-AIOpinionMonitor.ps1",
    "Stop-AIOpinionMonitor.ps1",
    "Run-AIOpinionMonitor.py",
    $StartCmdName,
    $StopCmdName
)
foreach ($Asset in $ExpectedAssets) {
    Assert-True (Test-Path -LiteralPath (Join-Path $LauncherSource $Asset) -PathType Leaf) "Missing launcher asset: $Asset"
}

$ResolvedProduct = (Resolve-Path -LiteralPath $ProductRoot).Path
$TempPrefix = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
Assert-True $ResolvedProduct.StartsWith($TempPrefix, [StringComparison]::OrdinalIgnoreCase) "ProductRoot must be a disposable directory under the system temp directory."
Assert-True (Test-Path -LiteralPath (Join-Path $ResolvedProduct "INTERNAL-PROTOTYPE-NOT-FOR-DISTRIBUTION.txt") -PathType Leaf) "ProductRoot is not marked as an internal prototype."

$RuntimeLauncher = Join-Path $ResolvedProduct ".runtime\launcher"
New-Item -ItemType Directory -Path $RuntimeLauncher -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $LauncherSource "Start-AIOpinionMonitor.ps1") -Destination $RuntimeLauncher
Copy-Item -LiteralPath (Join-Path $LauncherSource "Stop-AIOpinionMonitor.ps1") -Destination $RuntimeLauncher
Copy-Item -LiteralPath (Join-Path $LauncherSource "Run-AIOpinionMonitor.py") -Destination $RuntimeLauncher
Copy-Item -LiteralPath (Join-Path $LauncherSource $StartCmdName) -Destination $ResolvedProduct
Copy-Item -LiteralPath (Join-Path $LauncherSource $StopCmdName) -Destination $ResolvedProduct
$StartCmd = Join-Path $ResolvedProduct $StartCmdName
$StopCmd = Join-Path $ResolvedProduct $StopCmdName

$MainConfigPath = Join-Path $ResolvedProduct ".venv\pyvenv.cfg"
$StaleRoot = "C:\stale-aom-prototype-path"
$StalePythonRoot = Join-Path $StaleRoot ".runtime\python"
$StaleConfig = @(
    "home = $StalePythonRoot",
    "include-system-site-packages = false",
    "version = 3.13.9",
    "executable = $(Join-Path $StalePythonRoot 'python.exe')",
    "command = $(Join-Path $StalePythonRoot 'python.exe') -m venv --without-pip $(Join-Path $StaleRoot '.venv')"
) -join [Environment]::NewLine
$StaleConfig += [Environment]::NewLine
[IO.File]::WriteAllText($MainConfigPath, $StaleConfig, [Text.UTF8Encoding]::new($false))

$StateRoot = Join-Path ([IO.Path]::GetTempPath()) ("aom launcher test " + [Guid]::NewGuid().ToString("N"))
$StartScript = Join-Path $RuntimeLauncher "Start-AIOpinionMonitor.ps1"
$StopScript = Join-Path $RuntimeLauncher "Stop-AIOpinionMonitor.ps1"
$StatePath = Join-Path $StateRoot "server-state.json"
$ExpectedServerPython = Join-Path $ResolvedProduct ".runtime\python\pythonw.exe"
$SavedEnvironment = @{}
$CredentialNames = @("BAIDU_QIANFAN_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")
$LauncherEnvironmentNames = @(
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
$SyntheticSecretPrefix = "AOM_TEST_SECRET_" + [Guid]::NewGuid().ToString("N")
foreach ($Name in $CredentialNames + $LauncherEnvironmentNames) {
    $Value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ($null -ne $Value) {
        $SavedEnvironment[$Name] = $Value
    }
}
$PoisonPythonHome = Join-Path ([IO.Path]::GetTempPath()) ("aom pythonhome poison " + [Guid]::NewGuid().ToString("N"))
$PoisonPythonPath = Join-Path ([IO.Path]::GetTempPath()) ("aom pythonpath poison " + [Guid]::NewGuid().ToString("N"))
$StartedProcessId = $null
$StartedProcessStartTimeUtcTicks = $null
try {
    foreach ($Name in $CredentialNames) {
        Set-Item -LiteralPath "Env:$Name" -Value "$SyntheticSecretPrefix-$Name"
    }
    New-Item -ItemType Directory -Path $PoisonPythonHome -Force | Out-Null
    New-Item -ItemType Directory -Path $PoisonPythonPath -Force | Out-Null
    [IO.File]::WriteAllText(
        (Join-Path $PoisonPythonPath "sitecustomize.py"),
        "raise SystemExit('PYTHONPATH poison loaded')",
        [Text.UTF8Encoding]::new($false)
    )
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $PoisonPythonHome "Lib\encodings") -PathType Container)) "PYTHONHOME poison unexpectedly contains a standard library."
    Assert-True (Test-Path -LiteralPath (Join-Path $PoisonPythonPath "sitecustomize.py") -PathType Leaf) "PYTHONPATH poison was not created."
    $env:PYTHONHOME = $PoisonPythonHome
    $env:PYTHONPATH = $PoisonPythonPath
    $ExpectedTestEnvironment = @{}
    foreach ($Name in $CredentialNames + $LauncherEnvironmentNames) {
        $ExpectedTestEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
    }

    $QuotedStateRoot = '"' + $StateRoot + '"'
    Invoke-UserCommand `
        -Path $StartCmd `
        -Arguments @("-NoBrowser", "-BasePort", "18820", "-StartupTimeoutSeconds", "20", "-StateRoot", $QuotedStateRoot) `
        -CleanupScript $StopScript `
        -CleanupStateRoot $StateRoot
    Assert-True (Test-Path -LiteralPath $StatePath -PathType Leaf) "Launcher did not create server-state.json."
    $FirstState = Get-Content -Raw -Encoding UTF8 -LiteralPath $StatePath | ConvertFrom-Json
    $StartedProcessId = [int]$FirstState.processId
    $StartedProcessStartTimeUtcTicks = [long]$FirstState.processStartTimeUtcTicks
    Assert-True ($FirstState.lifecycle -eq "READY") "Launcher state did not reach the READY lifecycle."
    Assert-True ($FirstState.productRoot -eq $ResolvedProduct) "Launcher state contains the wrong product root."
    Assert-True ($FirstState.pythonPath -eq (Join-Path $ResolvedProduct ".runtime\python\pythonw.exe")) "Launcher state contains the wrong Python path."
    Assert-True ([int]$FirstState.port -ge 18820 -and [int]$FirstState.port -lt 18840) "Launcher selected a port outside the allowed range."
    foreach ($ControlledPath in @($FirstState.stdoutLog, $FirstState.stderrLog, $FirstState.stopFile)) {
        Assert-True (Test-ChildPath ([string]$ControlledPath) $StateRoot) "Launcher state points outside the controlled state directory."
    }

    $RunningProcess = Get-Process -Id $StartedProcessId -ErrorAction Stop
    Assert-True ($RunningProcess.Path -eq $FirstState.pythonPath) "Launcher state PID does not belong to the private Python executable."
    $HealthResponse = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:{0}/api/auth/status" -f $FirstState.port) -TimeoutSec 3
    Assert-True ($HealthResponse.StatusCode -eq 200) "Launcher health endpoint did not return HTTP 200."
    $HealthPayload = $HealthResponse.Content | ConvertFrom-Json
    Assert-True ($HealthPayload.PSObject.Properties.Name -contains "ok" -and [bool]$HealthPayload.ok) "Launcher health endpoint did not report an OK application state."
    Assert-True ((@(Get-LoopbackListenerProcessIds ([int]$FirstState.port))) -contains $StartedProcessId) "The healthy loopback listener is not owned by the state PID."

    Invoke-UserCommand `
        -Path $StartCmd `
        -Arguments @("-NoBrowser", "-BasePort", "18820", "-StartupTimeoutSeconds", "20", "-StateRoot", $QuotedStateRoot) `
        -CleanupScript $StopScript `
        -CleanupStateRoot $StateRoot
    $SecondState = Get-Content -Raw -Encoding UTF8 -LiteralPath $StatePath | ConvertFrom-Json
    Assert-True ([int]$SecondState.processId -eq $StartedProcessId) "A second launch created another server process instead of reusing the verified one."

    $RepairedConfig = Get-Content -Raw -Encoding UTF8 -LiteralPath $MainConfigPath
    Assert-True ($RepairedConfig -notmatch [regex]::Escape($StaleRoot)) "Launcher did not repair the stale virtual-environment path."
    Assert-True ($RepairedConfig -match [regex]::Escape((Join-Path $ResolvedProduct ".runtime\python"))) "Launcher repaired pyvenv.cfg to the wrong private Python path."

    $StateScanText = [IO.File]::ReadAllText($StatePath)
    foreach ($Name in $CredentialNames) {
        Assert-True (-not $StateScanText.Contains("$SyntheticSecretPrefix-$Name")) "Launcher state contains a synthetic API credential."
    }

    $StopOutput = @(& $StopCmd -StateRoot $StateRoot)
    Assert-True ($LASTEXITCODE -eq 0) "The user-facing stop command failed with exit code $LASTEXITCODE."
    Assert-True (($StopOutput -join "`n") -match "STOP_MODE=GRACEFUL") "The user-facing stop command did not use the graceful shutdown path."
    Assert-True (-not (Get-Process -Id $StartedProcessId -ErrorAction SilentlyContinue)) "Stop launcher left the verified server process running."
    Assert-True (-not (Test-Path -LiteralPath $StatePath)) "Stop launcher left stale server-state.json behind."
    foreach ($LogPath in @([string]$FirstState.stdoutLog, [string]$FirstState.stderrLog)) {
        Assert-True (Test-Path -LiteralPath $LogPath -PathType Leaf) "Expected launcher log is missing after shutdown: $LogPath"
        $LogScanText = [IO.File]::ReadAllText($LogPath)
        foreach ($Name in $CredentialNames) {
            Assert-True (-not $LogScanText.Contains("$SyntheticSecretPrefix-$Name")) "Launcher logs contain a synthetic API credential."
        }
    }

    $CurrentProcess = Get-Process -Id $PID -ErrorAction Stop
    $FixtureStdoutLog = Join-Path $StateRoot "logs\fixture.stdout.log"
    $FixtureStderrLog = Join-Path $StateRoot "logs\fixture.stderr.log"
    $FixtureStopFile = Join-Path $StateRoot "20000101T000000Z-deadbeef.stop.request"
    $FixtureStopToken = [Guid]::NewGuid().ToString("N")
    $TamperedState = [ordered]@{
        schemaVersion = 1
        lifecycle = "READY"
        processId = $PID
        processStartTimeUtcTicks = $CurrentProcess.StartTime.ToUniversalTime().Ticks
        port = 18820
        productRoot = $ResolvedProduct
        pythonPath = Join-Path $ResolvedProduct ".runtime\python\pythonw.exe"
        stdoutLog = $FixtureStdoutLog
        stderrLog = $FixtureStderrLog
        stopFile = $FixtureStopFile
        stopToken = $FixtureStopToken
    }
    [IO.File]::WriteAllText(
        $StatePath,
        ($TamperedState | ConvertTo-Json -Depth 4),
        [Text.UTF8Encoding]::new($false)
    )
    $RefusedTamperedState = $false
    try {
        & $StopScript -StateRoot $StateRoot
    }
    catch {
        $RefusedTamperedState = $_.Exception.Message -like "*PID verification failed*"
    }
    Assert-True $RefusedTamperedState "Stop launcher did not reject a state file pointing to a non-Python process."
    Assert-True ($null -ne (Get-Process -Id $PID -ErrorAction SilentlyContinue)) "Stop launcher terminated the test PowerShell process."
    Remove-Item -LiteralPath $StatePath -Force

    $StopSafetyFixturePath = Join-Path $StateRoot "stop-safety-fixture.py"
    $NestedStopSentinel = Join-Path $StateRoot "sensitive\20000101T000001Z-badc0ffe.stop.request"
    $InvalidNameStopSentinel = Join-Path $StateRoot "invalid-name.stop.request"
    $ForcedStopFile = Join-Path $StateRoot "20000101T000002Z-feedface.stop.request"
    $StopSafetyProcess = $null
    $StopSafetyProcessStartTimeUtcTicks = $null
    $UnsafeStopFileRefusals = 0
    try {
        [IO.File]::WriteAllText(
            $StopSafetyFixturePath,
            "import time`ntime.sleep(120)`n",
            [Text.UTF8Encoding]::new($false)
        )
        $StopSafetyProcess = Start-Process `
            -FilePath $ExpectedServerPython `
            -ArgumentList @("-I", "-B", ('"{0}"' -f $StopSafetyFixturePath)) `
            -WindowStyle Hidden `
            -PassThru
        $StopSafetyProcessStartTimeUtcTicks = $StopSafetyProcess.StartTime.ToUniversalTime().Ticks
        $UnsafeStopCases = @(
            [pscustomobject]@{
                Description = "a generated filename in a nested sensitive directory"
                Path = $NestedStopSentinel
                Marker = "UNCHANGED-NESTED-" + [Guid]::NewGuid().ToString("N")
            },
            [pscustomobject]@{
                Description = "an invalid filename directly under the runtime root"
                Path = $InvalidNameStopSentinel
                Marker = "UNCHANGED-NAME-" + [Guid]::NewGuid().ToString("N")
            }
        )
        foreach ($UnsafeStopCase in $UnsafeStopCases) {
            New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($UnsafeStopCase.Path)) -Force | Out-Null
            [IO.File]::WriteAllText(
                $UnsafeStopCase.Path,
                $UnsafeStopCase.Marker,
                [Text.UTF8Encoding]::new($false)
            )
            $UnsafeStopState = [ordered]@{
                schemaVersion = 1
                lifecycle = "READY"
                processId = $StopSafetyProcess.Id
                processStartTimeUtcTicks = $StopSafetyProcessStartTimeUtcTicks
                port = 18820
                productRoot = $ResolvedProduct
                pythonPath = $ExpectedServerPython
                stdoutLog = $FixtureStdoutLog
                stderrLog = $FixtureStderrLog
                stopFile = $UnsafeStopCase.Path
                stopToken = [Guid]::NewGuid().ToString("N")
            }
            [IO.File]::WriteAllText(
                $StatePath,
                ($UnsafeStopState | ConvertTo-Json -Depth 4),
                [Text.UTF8Encoding]::new($false)
            )
            $RefusedUnsafeStopFile = $false
            try {
                & $StopScript -StateRoot $StateRoot
            }
            catch {
                $RefusedUnsafeStopFile = $_.Exception.Message -like "*unsafe path or value*"
            }
            Assert-True $RefusedUnsafeStopFile "Stop launcher accepted $($UnsafeStopCase.Description)."
            Assert-True (Test-Path -LiteralPath $StatePath -PathType Leaf) "Stop launcher removed state after rejecting $($UnsafeStopCase.Description)."
            Assert-True ([IO.File]::ReadAllText($UnsafeStopCase.Path) -eq $UnsafeStopCase.Marker) "Stop launcher changed or deleted the protected sentinel for $($UnsafeStopCase.Description)."
            $StopSafetyCurrentProcess = Get-Process -Id $StopSafetyProcess.Id -ErrorAction SilentlyContinue
            Assert-True (
                Test-ProcessIdentity `
                    -Process $StopSafetyCurrentProcess `
                    -ExpectedPath $ExpectedServerPython `
                    -ExpectedStartTimeUtcTicks $StopSafetyProcessStartTimeUtcTicks
            ) "Stop launcher changed the verified process after rejecting $($UnsafeStopCase.Description)."
            $UnsafeStopFileRefusals++
            Remove-Item -LiteralPath $StatePath -Force
        }

        $ForcedStopState = [ordered]@{
            schemaVersion = 1
            lifecycle = "READY"
            processId = $StopSafetyProcess.Id
            processStartTimeUtcTicks = $StopSafetyProcessStartTimeUtcTicks
            port = 18820
            productRoot = $ResolvedProduct
            pythonPath = $ExpectedServerPython
            stdoutLog = $FixtureStdoutLog
            stderrLog = $FixtureStderrLog
            stopFile = $ForcedStopFile
            stopToken = [Guid]::NewGuid().ToString("N")
        }
        [IO.File]::WriteAllText(
            $StatePath,
            ($ForcedStopState | ConvertTo-Json -Depth 4),
            [Text.UTF8Encoding]::new($false)
        )
        $ForcedStopOutput = @(& $StopScript -StateRoot $StateRoot)
        Assert-True (($ForcedStopOutput -join "`n") -match "STOP_MODE=FORCED_TREE") "Stop launcher did not exercise its forced process-tree cleanup path."
        Assert-True $StopSafetyProcess.WaitForExit(0) "Forced stop did not prove that the exact fixture process exited."
        Assert-True (-not (Test-Path -LiteralPath $StatePath)) "Forced stop left stale server-state.json behind."
        Assert-True (-not (Test-Path -LiteralPath $ForcedStopFile)) "Forced stop left its request file behind."
    }
    finally {
        Remove-Item -LiteralPath $StatePath -Force -ErrorAction SilentlyContinue
        foreach ($OwnedStopFixtureFile in @($NestedStopSentinel, $InvalidNameStopSentinel, $ForcedStopFile, $StopSafetyFixturePath)) {
            Remove-Item -LiteralPath $OwnedStopFixtureFile -Force -ErrorAction SilentlyContinue
        }
        if ($null -ne $StopSafetyProcess) {
            $StopSafetyRemainingProcess = Get-Process -Id $StopSafetyProcess.Id -ErrorAction SilentlyContinue
            if (
                Test-ProcessIdentity `
                    -Process $StopSafetyRemainingProcess `
                    -ExpectedPath $ExpectedServerPython `
                    -ExpectedStartTimeUtcTicks $StopSafetyProcessStartTimeUtcTicks
            ) {
                Stop-Process -InputObject $StopSafetyRemainingProcess -Force -ErrorAction SilentlyContinue
            }
        }
    }

    $ForeignState = [ordered]@{
        schemaVersion = 1
        lifecycle = "READY"
        processId = $PID
        processStartTimeUtcTicks = $CurrentProcess.StartTime.ToUniversalTime().Ticks
        port = 18820
        productRoot = "C:\foreign-aom-product"
        pythonPath = $CurrentProcess.Path
        stdoutLog = $FixtureStdoutLog
        stderrLog = $FixtureStderrLog
        stopFile = $FixtureStopFile
        stopToken = $FixtureStopToken
    }
    [IO.File]::WriteAllText(
        $StatePath,
        ($ForeignState | ConvertTo-Json -Depth 4),
        [Text.UTF8Encoding]::new($false)
    )
    $RefusedForeignProcess = $false
    try {
        & $StartScript -NoBrowser -BasePort 18820 -StartupTimeoutSeconds 20 -StateRoot $StateRoot
    }
    catch {
        $RefusedForeignProcess = $_.Exception.Message -like "*Another verified portable copy is already running*"
    }
    Assert-True $RefusedForeignProcess "Start launcher did not preserve and reject a verified process belonging to another portable copy."
    Assert-True (Test-Path -LiteralPath $StatePath -PathType Leaf) "Start launcher deleted a live foreign state file."
    Assert-True ($null -ne (Get-Process -Id $PID -ErrorAction SilentlyContinue)) "Start launcher terminated the test PowerShell process."
    Remove-Item -LiteralPath $StatePath -Force

    $UnsafeStateRoot = Join-Path $LauncherSource ("must-not-create-" + [Guid]::NewGuid().ToString("N"))
    $RefusedUnsafeStateRoot = $false
    try {
        & $StartScript -NoBrowser -StateRoot $UnsafeStateRoot
    }
    catch {
        $RefusedUnsafeStateRoot = $_.Exception.Message -like "*permitted only under the system temporary directory*"
    }
    Assert-True $RefusedUnsafeStateRoot "Launcher accepted a custom StateRoot outside the system temporary directory."
    Assert-True (-not (Test-Path -LiteralPath $UnsafeStateRoot)) "Launcher wrote to a rejected custom StateRoot."

    $WriteFailureStateRoot = Join-Path ([IO.Path]::GetTempPath()) ("aom-launcher-write-failure-" + [Guid]::NewGuid().ToString("N"))
    $BlockedStatePath = Join-Path $WriteFailureStateRoot "server-state.json"
    New-Item -ItemType Directory -Path $BlockedStatePath -Force | Out-Null
    $BeforeServerIds = @(
        Get-Process -Name "pythonw" -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -eq $ExpectedServerPython } |
            ForEach-Object { $_.Id }
    )
    $StateWriteFailureObserved = $false
    try {
        & $StartScript -NoBrowser -BasePort 18860 -StartupTimeoutSeconds 20 -StateRoot $WriteFailureStateRoot
    }
    catch {
        $StateWriteFailureObserved = $_.Exception.Message -like "*Failed to persist STARTING launcher state:*"
    }
    Assert-True $StateWriteFailureObserved "Launcher did not report the expected STARTING-state persistence failure."
    Start-Sleep -Milliseconds 250
    $AfterServerIds = @(
        Get-Process -Name "pythonw" -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -eq $ExpectedServerPython } |
            ForEach-Object { $_.Id }
    )
    $UnexpectedServerIds = @($AfterServerIds | Where-Object { $_ -notin $BeforeServerIds })
    Assert-True ($UnexpectedServerIds.Count -eq 0) "Launcher left an orphaned server root after state persistence failed."

    $RuntimeRunnerPath = Join-Path $RuntimeLauncher "Run-AIOpinionMonitor.py"
    $OriginalRuntimeRunner = [IO.File]::ReadAllBytes($RuntimeRunnerPath)
    $TreeFailureStateRoot = Join-Path ([IO.Path]::GetTempPath()) ("aom tree cleanup test " + [Guid]::NewGuid().ToString("N"))
    $TreeRootPidPath = Join-Path $TreeFailureStateRoot "tree-root.pid"
    $TreeChildPidPath = Join-Path $TreeFailureStateRoot "tree-child.pid"
    $TreeGrandchildPidPath = Join-Path $TreeFailureStateRoot "tree-grandchild.pid"
    $TreeIdentitiesPath = Join-Path $TreeFailureStateRoot "tree-identities.json"
    $TreeIdentityErrorPath = Join-Path $TreeFailureStateRoot "tree-identity-error.txt"
    $TreePortPath = Join-Path $TreeFailureStateRoot "tree-port.txt"
    $TreeStopSeenPath = Join-Path $TreeFailureStateRoot "tree-stop-seen.txt"
    $TreeFixtureProcessIdentities = @()
    $TreeFixtureProcessIds = @()
    $TreeRemainingProcessIds = @()
    $TreeUnverifiedCleanupProcessIds = @()
    $TreeStartFailureObserved = $false
    $TreeFixtureReady = $false
    $TreeStopRequestObserved = $false
    $TreeStateRemoved = $false
    $TreeStopFileRemoved = $false
    $TreePort = 0
    $TreeIdentityErrorText = ""
    $RunnerRestoreFailure = $null
    $NonResponsiveRunner = @'
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
import traceback
from ctypes import wintypes
from pathlib import Path


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.GetProcessTimes.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
]
kernel32.GetProcessTimes.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


def process_start_time_utc_ticks(process_id: int) -> int:
    handle = kernel32.OpenProcess(0x1000, False, process_id)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        created = wintypes.FILETIME()
        exited = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        windows_ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
        return windows_ticks + 504_911_232_000_000_000
    finally:
        kernel32.CloseHandle(handle)


state_root = Path(os.environ["AOM_LAUNCHER_STOP_FILE"]).parent
child_script = state_root / "tree-child.py"
child_script.write_text(
    "import os, subprocess, sys, time\n"
    "from pathlib import Path\n"
    "root = Path(sys.argv[1])\n"
    "grandchild = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'import time; time.sleep(120)'])\n"
    "(root / 'tree-grandchild.pid').write_text(str(grandchild.pid), encoding='ascii')\n"
    "time.sleep(120)\n",
    encoding="utf-8",
)
child = subprocess.Popen([sys.executable, "-I", "-B", str(child_script), str(state_root)])
(state_root / "tree-root.pid").write_text(str(os.getpid()), encoding="ascii")
(state_root / "tree-child.pid").write_text(str(child.pid), encoding="ascii")
(state_root / "tree-port.txt").write_text(sys.argv[sys.argv.index("--port") + 1], encoding="ascii")
ready_deadline = time.monotonic() + 4
while time.monotonic() < ready_deadline and not (state_root / "tree-grandchild.pid").is_file():
    time.sleep(0.05)
try:
    if (state_root / "tree-grandchild.pid").is_file():
        grandchild_pid = int((state_root / "tree-grandchild.pid").read_text(encoding="ascii"))
        identities = [
            {
                "processId": process_id,
                "processStartTimeUtcTicks": process_start_time_utc_ticks(process_id),
            }
            for process_id in (os.getpid(), child.pid, grandchild_pid)
        ]
        (state_root / "tree-identities.json").write_text(
            json.dumps(identities),
            encoding="ascii",
        )
except Exception:
    (state_root / "tree-identity-error.txt").write_text(
        traceback.format_exc(),
        encoding="utf-8",
    )
stop_file = Path(os.environ["AOM_LAUNCHER_STOP_FILE"])
stop_token = os.environ["AOM_LAUNCHER_STOP_TOKEN"]
while True:
    try:
        if stop_file.is_file() and stop_file.read_text(encoding="ascii").strip() == stop_token:
            (state_root / "tree-stop-seen.txt").write_text("seen", encoding="ascii")
            break
    except OSError:
        pass
    time.sleep(0.05)
time.sleep(120)
'@
    try {
        [IO.File]::WriteAllText($RuntimeRunnerPath, $NonResponsiveRunner, [Text.UTF8Encoding]::new($false))
        try {
            & $StartScript -NoBrowser -BasePort 18880 -StartupTimeoutSeconds 5 -StateRoot $TreeFailureStateRoot
        }
        catch {
            $TreeStartFailureObserved = $_.Exception.Message -like "*software failed to start*"
        }
        $TreeFixtureReady = (
            (Test-Path -LiteralPath $TreeRootPidPath -PathType Leaf) -and
            (Test-Path -LiteralPath $TreeChildPidPath -PathType Leaf) -and
            (Test-Path -LiteralPath $TreeGrandchildPidPath -PathType Leaf) -and
            (Test-Path -LiteralPath $TreeIdentitiesPath -PathType Leaf) -and
            (Test-Path -LiteralPath $TreePortPath -PathType Leaf)
        )
        if (Test-Path -LiteralPath $TreeIdentitiesPath -PathType Leaf) {
            $ParsedTreeIdentities = Get-Content -Raw -Encoding ASCII -LiteralPath $TreeIdentitiesPath | ConvertFrom-Json
            foreach ($Identity in $ParsedTreeIdentities) {
                $TreeFixtureProcessIdentities += [pscustomobject]@{
                    ProcessId = [int]$Identity.processId
                    ProcessStartTimeUtcTicks = [long]$Identity.processStartTimeUtcTicks
                }
            }
        }
        if (Test-Path -LiteralPath $TreeIdentityErrorPath -PathType Leaf) {
            $TreeIdentityErrorText = Get-Content -Raw -Encoding UTF8 -LiteralPath $TreeIdentityErrorPath
        }
        $TreeFixtureProcessIds = @($TreeFixtureProcessIdentities | ForEach-Object { $_.ProcessId })
        $TreeFixtureReady = (
            $TreeFixtureReady -and
            $TreeFixtureProcessIdentities.Count -eq 3 -and
            @($TreeFixtureProcessIds | Select-Object -Unique).Count -eq 3
        )
        if (Test-Path -LiteralPath $TreePortPath -PathType Leaf) {
            $TreePort = [int]([IO.File]::ReadAllText($TreePortPath).Trim())
        }
        $TreeRemainingProcessIds = @(
            foreach ($Identity in $TreeFixtureProcessIdentities) {
                $TreeFixtureProcess = Get-Process -Id $Identity.ProcessId -ErrorAction SilentlyContinue
                if (
                    Test-ProcessIdentity `
                        -Process $TreeFixtureProcess `
                        -ExpectedPath $ExpectedServerPython `
                        -ExpectedStartTimeUtcTicks $Identity.ProcessStartTimeUtcTicks
                ) {
                    $Identity.ProcessId
                }
            }
        )
        $TreeStopRequestObserved = Test-Path -LiteralPath $TreeStopSeenPath -PathType Leaf
        $TreeStateRemoved = -not (Test-Path -LiteralPath (Join-Path $TreeFailureStateRoot "server-state.json"))
        $TreeStopFileRemoved = @(Get-ChildItem -LiteralPath $TreeFailureStateRoot -Filter "*.stop.request" -File -ErrorAction SilentlyContinue).Count -eq 0
    }
    finally {
        try {
            [IO.File]::WriteAllBytes($RuntimeRunnerPath, $OriginalRuntimeRunner)
        }
        catch {
            $RunnerRestoreFailure = $_.Exception
        }
        $TreeCleanupIdentities = @($TreeFixtureProcessIdentities)
        [array]::Reverse($TreeCleanupIdentities)
        foreach ($Identity in $TreeCleanupIdentities) {
            $TreeFixtureProcess = Get-Process -Id $Identity.ProcessId -ErrorAction SilentlyContinue
            if (
                Test-ProcessIdentity `
                    -Process $TreeFixtureProcess `
                    -ExpectedPath $ExpectedServerPython `
                    -ExpectedStartTimeUtcTicks $Identity.ProcessStartTimeUtcTicks
            ) {
                Stop-Process -InputObject $TreeFixtureProcess -Force -ErrorAction SilentlyContinue
            }
            elseif ($null -ne $TreeFixtureProcess) {
                $TreeUnverifiedCleanupProcessIds += $Identity.ProcessId
            }
        }
    }
    Assert-True ($null -eq $RunnerRestoreFailure) "The test could not restore the product runner after the failure fixture."
    Assert-True $TreeStartFailureObserved "The non-responsive runner did not produce the expected startup failure."
    Assert-True $TreeFixtureReady "The non-responsive runner did not record its exact process tree and port. $TreeIdentityErrorText"
    Assert-True ($TreeUnverifiedCleanupProcessIds.Count -eq 0) "The test refused to clean a process whose recorded identity could not be verified."
    Assert-True $TreeStopRequestObserved "Startup failure cleanup did not send the graceful stop token first."
    Assert-True ($TreeRemainingProcessIds.Count -eq 0) "Startup failure cleanup left a recorded process-tree member running."
    Assert-True $TreeStateRemoved "Startup failure cleanup left its verified state file behind."
    Assert-True $TreeStopFileRemoved "Startup failure cleanup left its stop request file behind."
    Assert-True ((@(Get-LoopbackListenerProcessIds $TreePort)).Count -eq 0) "The failed-start fixture left its loopback port listening."

    Assert-EnvironmentMatches `
        -Expected $ExpectedTestEnvironment `
        -Names ($CredentialNames + $LauncherEnvironmentNames) `
        -Context "The launcher"
}
finally {
    $CleanupIdentityVerified = $false
    if (
        $null -ne $StartedProcessId -and
        $null -ne $StartedProcessStartTimeUtcTicks -and
        (Test-Path -LiteralPath $StatePath -PathType Leaf)
    ) {
        try {
            $CleanupState = Get-Content -Raw -Encoding UTF8 -LiteralPath $StatePath | ConvertFrom-Json
            $CleanupIdentityVerified = (
                [int]$CleanupState.processId -eq $StartedProcessId -and
                [long]$CleanupState.processStartTimeUtcTicks -eq $StartedProcessStartTimeUtcTicks -and
                $CleanupState.productRoot -eq $ResolvedProduct -and
                $CleanupState.pythonPath -eq (Join-Path $ResolvedProduct ".runtime\python\pythonw.exe")
            )
        }
        catch {
            $CleanupIdentityVerified = $false
        }
    }
    if ($CleanupIdentityVerified) {
        try {
            & $StopScript -StateRoot $StateRoot | Out-Null
        }
        catch {
        }
        $RemainingProcess = Get-Process -Id $StartedProcessId -ErrorAction SilentlyContinue
        if ($null -ne $RemainingProcess) {
            try {
                if (
                    $RemainingProcess.Path -eq (Join-Path $ResolvedProduct ".runtime\python\pythonw.exe") -and
                    $RemainingProcess.StartTime.ToUniversalTime().Ticks -eq $StartedProcessStartTimeUtcTicks
                ) {
                    $TaskkillPath = Join-Path ([Environment]::SystemDirectory) "taskkill.exe"
                    & $TaskkillPath /PID $StartedProcessId /T /F | Out-Null
                }
            }
            catch {
            }
        }
    }
    foreach ($Name in $CredentialNames + $LauncherEnvironmentNames) {
        if ($SavedEnvironment.ContainsKey($Name)) {
            Set-Item -LiteralPath "Env:$Name" -Value $SavedEnvironment[$Name]
        }
        else {
            Remove-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue
        }
    }
}

foreach ($Name in $CredentialNames + $LauncherEnvironmentNames) {
    $ExpectedValue = if ($SavedEnvironment.ContainsKey($Name)) { $SavedEnvironment[$Name] } else { $null }
    $ActualValue = [Environment]::GetEnvironmentVariable($Name, "Process")
    Assert-True ($ActualValue -eq $ExpectedValue) "The launcher test did not restore caller environment variable: $Name"
}

Write-Output "SOURCE_CMD_INTEGRATION=PASS"
Write-Output "WINDOWS_POWERSHELL=5.1"
Write-Output "CMD_ENTRY_SOURCE_INTEGRATION=PASS"
Write-Output "REAL_CALLER_API_KEYS_EXPOSED_DURING_TEST=0"
Write-Output "SYNTHETIC_API_KEYS_IN_STATE_AND_LOGS=0"
Write-Output "HEALTH_CHECK_TARGET=127.0.0.1"
Write-Output "LISTENER_PID_BOUND=PASS"
Write-Output "GRACEFUL_SERVER_EXIT=PASS"
Write-Output "PYTHONHOME_POISON_IGNORED=PASS"
Write-Output "PYTHONPATH_POISON_IGNORED=PASS"
Write-Output "TAMPERED_PROCESS_REFUSALS=2"
Write-Output "UNSAFE_STOP_FILE_REFUSALS=2"
Write-Output "FORCED_STOP_PATH=PASS"
Write-Output "UNSAFE_STATE_ROOT_WRITES=0"
Write-Output "CALLER_ENVIRONMENT_RESTORED=$($CredentialNames.Count + $LauncherEnvironmentNames.Count)"
Write-Output "ORPHANED_SERVER_ROOTS_AFTER_STATE_WRITE_FAILURE=0"
Write-Output "FAILED_START_PROCESS_TREE_CLEANUP=PASS"
