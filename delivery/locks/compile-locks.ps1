[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$PythonPath,

    [string]$CacheDir = (Join-Path ([IO.Path]::GetTempPath()) "ai-opinion-delivery-uv-cache")
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ExpectedPythonVersion = "3.13.9"
$ExpectedUvVersion = "uv 0.10.8 (c021be36a 2026-03-03)"
$ExpectedUvSha256 = "067CF5D81A2DC006C1C76FA160B4DA96A35BC80900C22FAED7ACFC52510FCDF5"
$TargetPlatform = "x86_64-pc-windows-msvc"
$ExcludeNewer = "2026-08-29T15:59:59Z"

$RepoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$ResolvedPython = (Resolve-Path -LiteralPath $PythonPath).Path
$ResolvedCacheDir = [IO.Path]::GetFullPath($CacheDir)
$VenvRoot = Split-Path -Parent (Split-Path -Parent $ResolvedPython)
$VenvConfig = Join-Path $VenvRoot "pyvenv.cfg"

if (-not (Test-Path -LiteralPath $VenvConfig -PathType Leaf)) {
    throw "PythonPath must point to python.exe in an isolated virtual environment."
}

$VenvConfigText = Get-Content -LiteralPath $VenvConfig -Raw
if ($VenvConfigText -notmatch "(?im)^include-system-site-packages\s*=\s*false\s*$") {
    throw "The virtual environment must set include-system-site-packages = false."
}

$PythonProbe = "import platform,struct,sys,sysconfig;print('|'.join((platform.python_version(),str(struct.calcsize('P')*8),platform.python_implementation(),str(sys.prefix != sys.base_prefix),sys.platform,sysconfig.get_platform())))"
$PythonInfo = (& $ResolvedPython -I -c $PythonProbe).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect the target Python interpreter."
}
$PythonInfo = $PythonInfo -split "\|", 6
if ($PythonInfo.Count -ne 6) {
    throw "Unexpected target Python probe output."
}
if (
    $PythonInfo[0] -ne $ExpectedPythonVersion -or
    $PythonInfo[1] -ne "64" -or
    $PythonInfo[2] -ne "CPython" -or
    $PythonInfo[3] -ne "True" -or
    $PythonInfo[4] -ne "win32" -or
    $PythonInfo[5] -ne "win-amd64"
) {
    throw "An isolated win-amd64 CPython $ExpectedPythonVersion interpreter is required."
}

$UvCommand = Get-Command uv -CommandType Application -ErrorAction Stop | Select-Object -First 1
$UvPath = $UvCommand.Source
$UvVersion = (& $UvPath --version).Trim()
if ($LASTEXITCODE -ne 0 -or $UvVersion -ne $ExpectedUvVersion) {
    throw "Expected $ExpectedUvVersion; found $UvVersion."
}
$UvSha256 = (Get-FileHash -LiteralPath $UvPath -Algorithm SHA256).Hash.ToUpperInvariant()
if ($UvSha256 -ne $ExpectedUvSha256) {
    throw "uv.exe SHA256 mismatch; refusing to generate lock files."
}

# Lock generation does not need product secrets. Clear index overrides so private
# addresses or credentials cannot be written into generated artifacts.
$EnvironmentNamesToClear = @(
    "BAIDU_QIANFAN_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "PIP_CONFIG_FILE",
    "PIP_EXTRA_INDEX_URL",
    "PIP_FIND_LINKS",
    "PIP_INDEX_URL",
    "PIP_NO_BINARY",
    "PIP_ONLY_BINARY",
    "PIP_TRUSTED_HOST",
    "UV_BUILD_CONSTRAINT",
    "UV_CONFIG_FILE",
    "UV_CONSTRAINT",
    "UV_DEFAULT_INDEX",
    "UV_EXCLUDE",
    "UV_EXTRA_INDEX_URL",
    "UV_FIND_LINKS",
    "UV_INDEX",
    "UV_INDEX_URL",
    "UV_INSECURE_HOST",
    "UV_KEYRING_PROVIDER",
    "UV_LINK_MODE",
    "UV_NO_BINARY",
    "UV_NO_BUILD_ISOLATION",
    "UV_OFFLINE",
    "UV_ONLY_BINARY",
    "UV_OVERRIDE",
    "UV_PRERELEASE",
    "UV_PYTHON",
    "UV_PYTHON_PLATFORM",
    "UV_PYTHON_VERSION",
    "UV_RESOLUTION"
)
$SavedEnvironment = @{}
$EnvironmentSanitized = $false

$CommonArguments = @(
    "--no-config",
    "--cache-dir", $ResolvedCacheDir,
    "--no-python-downloads",
    "--no-progress",
    "--quiet",
    "--color", "never",
    "pip", "compile",
    "--default-index", "https://pypi.org/simple",
    "--index-strategy", "first-index",
    "--keyring-provider", "disabled",
    "--resolution", "highest",
    "--prerelease", "disallow",
    "--exclude-newer", $ExcludeNewer,
    "--python", $ResolvedPython,
    "--python-version", $ExpectedPythonVersion,
    "--python-platform", $TargetPlatform,
    "--generate-hashes",
    "--only-binary", ":all:",
    "--no-binary", "jieba",
    "--no-binary", "qrcode-terminal",
    "--no-sources",
    "--refresh",
    "--custom-compile-command", "powershell -File delivery/locks/compile-locks.ps1 -PythonPath <isolated-python>"
)

function Invoke-LockCompile {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$InputFiles,

        [Parameter(Mandatory = $true)]
        [string]$OutputFile
    )

    $Arguments = @($CommonArguments) + $InputFiles + @("--output-file", $OutputFile)
    & $UvPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency lock generation failed: $OutputFile"
    }
}

function Assert-LockPolicy {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LockFile
    )

    $LockText = Get-Content -LiteralPath $LockFile -Raw
    $ForbiddenPatterns = @(
        "(?im)^\s*--(?:index-url|extra-index-url|find-links|trusted-host)\b",
        "(?im)^\s*(?:-e|--editable)\s+",
        "(?im)^[^#\r\n]*\s@\s*\S+",
        "(?im)^\s*(?:git\+|https?://|file:|\.{1,2}[\\/]|[A-Za-z]:[\\/]|\\\\)"
    )
    foreach ($Pattern in $ForbiddenPatterns) {
        if ($LockText -match $Pattern) {
            throw "Forbidden source or index directive found in lock: $LockFile"
        }
    }
    if ($LockText -notmatch "--hash=sha256:") {
        throw "No SHA256 hashes found in lock: $LockFile"
    }
}

$LockNames = @(
    "main-win11-x64-py313.lock.txt",
    "test-win11-x64-py313.lock.txt",
    "scrapling-win11-x64-py313.lock.txt",
    "bilibili-cli-runtime-win11-x64-py313.lock.txt",
    "newspaper4k-runtime-win11-x64-py313.lock.txt",
    "aiotieba-runtime-win11-x64-py313.lock.txt"
)
$LockRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$RunId = [Guid]::NewGuid().ToString("N")
$StageRoot = Join-Path $LockRoot ".generated-stage-$RunId"
$BackupRoot = Join-Path $LockRoot ".generated-backup-$RunId"
$GeneratedRoot = Join-Path $LockRoot "generated"
$LockRootPrefix = $LockRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar

foreach ($ManagedPath in @($StageRoot, $BackupRoot)) {
    $FullManagedPath = [IO.Path]::GetFullPath($ManagedPath)
    if (-not $FullManagedPath.StartsWith($LockRootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Managed staging path escaped the lock directory."
    }
}

Push-Location $RepoRoot
try {
    foreach ($Name in $EnvironmentNamesToClear) {
        $CurrentValue = [Environment]::GetEnvironmentVariable($Name, "Process")
        if ($null -ne $CurrentValue) {
            $SavedEnvironment[$Name] = $CurrentValue
        }
    }
    $EnvironmentSanitized = $true
    foreach ($Name in $EnvironmentNamesToClear) {
        Remove-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue
    }

    New-Item -ItemType Directory -Path $ResolvedCacheDir -Force | Out-Null
    New-Item -ItemType Directory -Path $StageRoot | Out-Null

    $StageLockFiles = foreach ($LockName in $LockNames) {
        Join-Path $StageRoot $LockName
    }

    Invoke-LockCompile -InputFiles @("delivery/locks/inputs/main.in") -OutputFile $StageLockFiles[0]
    Invoke-LockCompile -InputFiles @("delivery/locks/inputs/main.in", "delivery/locks/inputs/test.in") -OutputFile $StageLockFiles[1]
    Invoke-LockCompile -InputFiles @("delivery/locks/inputs/scrapling.in") -OutputFile $StageLockFiles[2]
    Invoke-LockCompile -InputFiles @("delivery/locks/inputs/bilibili-cli-runtime.in") -OutputFile $StageLockFiles[3]
    Invoke-LockCompile -InputFiles @("delivery/locks/inputs/newspaper4k-runtime.in") -OutputFile $StageLockFiles[4]
    Invoke-LockCompile -InputFiles @("delivery/locks/inputs/aiotieba-runtime.in") -OutputFile $StageLockFiles[5]
    foreach ($LockFile in $StageLockFiles) {
        Assert-LockPolicy -LockFile $LockFile
    }

    $ChecksumLines = for ($Index = 0; $Index -lt $StageLockFiles.Count; $Index++) {
        $LockFile = $StageLockFiles[$Index]
        $Hash = (Get-FileHash -LiteralPath $LockFile -Algorithm SHA256).Hash.ToLowerInvariant()
        "$Hash  $($LockNames[$Index])"
    }
    $ChecksumPath = Join-Path $StageRoot "SHA256SUMS.txt"
    [IO.File]::WriteAllText(
        $ChecksumPath,
        (($ChecksumLines -join "`n") + "`n"),
        [Text.UTF8Encoding]::new($false)
    )

    if (Test-Path -LiteralPath $GeneratedRoot) {
        Move-Item -LiteralPath $GeneratedRoot -Destination $BackupRoot
    }
    try {
        Move-Item -LiteralPath $StageRoot -Destination $GeneratedRoot
    }
    catch {
        if (
            (Test-Path -LiteralPath $BackupRoot) -and
            -not (Test-Path -LiteralPath $GeneratedRoot)
        ) {
            Move-Item -LiteralPath $BackupRoot -Destination $GeneratedRoot
        }
        throw
    }

    if (Test-Path -LiteralPath $BackupRoot) {
        Remove-Item -LiteralPath $BackupRoot -Recurse -Force
    }
}
finally {
    try {
        Pop-Location
        if (Test-Path -LiteralPath $StageRoot) {
            Remove-Item -LiteralPath $StageRoot -Recurse -Force
        }
        if (
            (Test-Path -LiteralPath $BackupRoot) -and
            -not (Test-Path -LiteralPath $GeneratedRoot)
        ) {
            Move-Item -LiteralPath $BackupRoot -Destination $GeneratedRoot
        }
    }
    finally {
        if ($EnvironmentSanitized) {
            foreach ($Name in $EnvironmentNamesToClear) {
                if ($SavedEnvironment.ContainsKey($Name)) {
                    Set-Item -LiteralPath "Env:$Name" -Value $SavedEnvironment[$Name]
                }
                else {
                    Remove-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue
                }
            }
        }
    }
}

Write-Output "Generated 6 hashed lock files for Windows 11 x64 / CPython 3.13.9."
