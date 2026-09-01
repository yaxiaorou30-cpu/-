[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$BasePythonPath,

    [string]$WorkRoot = (Join-Path ([IO.Path]::GetTempPath()) "aom-lock-verify"),

    [string]$CacheDir = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ExpectedPythonVersion = "3.13.9"
$ExpectedUvVersion = "uv 0.10.8 (c021be36a 2026-03-03)"
$ExpectedUvSha256 = "067CF5D81A2DC006C1C76FA160B4DA96A35BC80900C22FAED7ACFC52510FCDF5"
$ExcludeNewer = "2026-08-29T15:59:59Z"

$RepoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$RepoRootPrefix = $RepoRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$GeneratedRoot = Join-Path $PSScriptRoot "generated"
$ResolvedBasePython = (Resolve-Path -LiteralPath $BasePythonPath).Path
$ResolvedWorkRoot = [IO.Path]::GetFullPath($WorkRoot)

if (
    $ResolvedWorkRoot.Equals($RepoRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $ResolvedWorkRoot.StartsWith($RepoRootPrefix, [StringComparison]::OrdinalIgnoreCase)
) {
    throw "WorkRoot must be outside the repository."
}
if ($ResolvedWorkRoot.Length -gt 80) {
    throw "WorkRoot must be 80 characters or shorter for legacy Windows package builds."
}

$RunRoot = Join-Path $ResolvedWorkRoot ("run-" + [Guid]::NewGuid().ToString("N"))
if ([string]::IsNullOrWhiteSpace($CacheDir)) {
    $ResolvedCacheDir = Join-Path ([IO.Path]::GetTempPath()) "aom-lock-cache"
}
else {
    $ResolvedCacheDir = [IO.Path]::GetFullPath($CacheDir)
}
if (
    $ResolvedCacheDir.Equals($RepoRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $ResolvedCacheDir.StartsWith($RepoRootPrefix, [StringComparison]::OrdinalIgnoreCase)
) {
    throw "CacheDir must be outside the repository."
}
if ($ResolvedCacheDir.Length -gt 80) {
    throw "CacheDir must be 80 characters or shorter for legacy Windows package builds."
}

$BaseProbe = "import platform,struct,sys,sysconfig;print('|'.join((platform.python_version(),str(struct.calcsize('P')*8),platform.python_implementation(),sys.platform,sysconfig.get_platform())))"
$BaseInfo = (& $ResolvedBasePython -I -c $BaseProbe).Trim() -split "\|", 5
if (
    $LASTEXITCODE -ne 0 -or
    $BaseInfo.Count -ne 5 -or
    $BaseInfo[0] -ne $ExpectedPythonVersion -or
    $BaseInfo[1] -ne "64" -or
    $BaseInfo[2] -ne "CPython" -or
    $BaseInfo[3] -ne "win32" -or
    $BaseInfo[4] -ne "win-amd64"
) {
    throw "BasePythonPath must be win-amd64 CPython $ExpectedPythonVersion."
}

$UvCommand = Get-Command uv -CommandType Application -ErrorAction Stop
$UvPath = $UvCommand.Source
$UvVersion = (& $UvPath --version).Trim()
$UvSha256 = (Get-FileHash -LiteralPath $UvPath -Algorithm SHA256).Hash.ToUpperInvariant()
if (
    $LASTEXITCODE -ne 0 -or
    $UvVersion -ne $ExpectedUvVersion -or
    $UvSha256 -ne $ExpectedUvSha256
) {
    throw "The pinned uv executable is not available."
}

$LockSpecs = @(
    @{
        Name = "main"
        File = "main-win11-x64-py313.lock.txt"
        Smoke = "import apscheduler,bs4,cryptography,docx,jieba,jinja2,playwright,requests,yaml"
    },
    @{
        Name = "test"
        File = "test-win11-x64-py313.lock.txt"
        Smoke = "import apscheduler,bs4,cryptography,docx,jieba,jinja2,playwright,pytest,requests,yaml"
    },
    @{
        Name = "scrapling"
        File = "scrapling-win11-x64-py313.lock.txt"
        Smoke = "import patchright,playwright,scrapling"
    },
    @{
        Name = "bilibili-cli-runtime"
        File = "bilibili-cli-runtime-win11-x64-py313.lock.txt"
        Smoke = "import aiohttp,bilibili_api,browser_cookie3,click,qrcode,rich,yaml"
    },
    @{
        Name = "newspaper4k-runtime"
        File = "newspaper4k-runtime-win11-x64-py313.lock.txt"
        Smoke = "import PIL,brotli,bs4,dateutil,feedparser,jieba,lxml,requests,tldextract,typing_extensions,w3lib,yaml"
    },
    @{
        Name = "aiotieba-runtime"
        File = "aiotieba-runtime-win11-x64-py313.lock.txt"
        Smoke = "import aiohttp,bs4,cryptography,lxml,google.protobuf"
    }
)

$ExpectedLockNames = @($LockSpecs | ForEach-Object { $_.File } | Sort-Object)
$ActualLockNames = @(Get-ChildItem -LiteralPath $GeneratedRoot -Filter "*.lock.txt" -File | ForEach-Object { $_.Name } | Sort-Object)
if (($ExpectedLockNames -join "`n") -ne ($ActualLockNames -join "`n")) {
    throw "The generated lock set is incomplete or contains unexpected lock files."
}

$ChecksumPath = Join-Path $GeneratedRoot "SHA256SUMS.txt"
$ChecksumLines = @(Get-Content -LiteralPath $ChecksumPath | Where-Object { $_.Trim() })
if ($ChecksumLines.Count -ne $LockSpecs.Count) {
    throw "SHA256SUMS.txt does not contain one entry per lock."
}
$ExpectedChecksums = @{}
foreach ($Line in $ChecksumLines) {
    if ($Line -notmatch "^([0-9a-f]{64})  ([A-Za-z0-9._-]+)$") {
        throw "Invalid SHA256SUMS.txt entry."
    }
    $ExpectedChecksums[$Matches[2]] = $Matches[1]
}
foreach ($Spec in $LockSpecs) {
    if (-not $ExpectedChecksums.ContainsKey($Spec.File)) {
        throw "Missing checksum for $($Spec.File)."
    }
    $LockPath = Join-Path $GeneratedRoot $Spec.File
    $ActualHash = (Get-FileHash -LiteralPath $LockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualHash -ne $ExpectedChecksums[$Spec.File]) {
        throw "Checksum mismatch for $($Spec.File)."
    }
}

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
    "UV_PYTHON"
)
$SavedEnvironment = @{}
foreach ($Name in $EnvironmentNamesToClear) {
    $CurrentValue = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ($null -ne $CurrentValue) {
        $SavedEnvironment[$Name] = $CurrentValue
    }
}

New-Item -ItemType Directory -Path $RunRoot | Out-Null
New-Item -ItemType Directory -Path $ResolvedCacheDir -Force | Out-Null

try {
    foreach ($Name in $EnvironmentNamesToClear) {
        Remove-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue
    }

    foreach ($Spec in $LockSpecs) {
        $VenvRoot = Join-Path $RunRoot $Spec.Name
        & $ResolvedBasePython -I -m venv --copies --without-pip $VenvRoot
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create isolated environment: $($Spec.Name)"
        }

        $PythonPath = Join-Path $VenvRoot "Scripts\python.exe"
        $VenvConfig = Get-Content -LiteralPath (Join-Path $VenvRoot "pyvenv.cfg") -Raw
        if ($VenvConfig -notmatch "(?im)^include-system-site-packages\s*=\s*false\s*$") {
            throw "System site packages are enabled in $($Spec.Name)."
        }

        $SyncArguments = @(
            "--no-config",
            "--cache-dir", $ResolvedCacheDir,
            "--no-python-downloads",
            "--no-progress",
            "--quiet",
            "--color", "never",
            "pip", "sync",
            "--python", $PythonPath,
            "--default-index", "https://pypi.org/simple",
            "--index-strategy", "first-index",
            "--keyring-provider", "disabled",
            "--exclude-newer", $ExcludeNewer,
            "--require-hashes",
            "--strict",
            "--only-binary", ":all:",
            "--no-binary", "jieba",
            "--no-binary", "bilibili-api-python",
            "--no-binary", "qrcode-terminal",
            "--no-sources",
            "--link-mode", "copy",
            (Join-Path $GeneratedRoot $Spec.File)
        )
        & $UvPath @SyncArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Hashed sync failed: $($Spec.Name)"
        }

        & $UvPath --no-config --cache-dir $ResolvedCacheDir --no-python-downloads --quiet pip check --python $PythonPath
        if ($LASTEXITCODE -ne 0) {
            throw "Dependency check failed: $($Spec.Name)"
        }

        & $PythonPath -I -B -c $Spec.Smoke
        if ($LASTEXITCODE -ne 0) {
            throw "Import smoke failed: $($Spec.Name)"
        }
        Write-Output "VERIFIED $($Spec.Name)"
    }
}
finally {
    foreach ($Name in $EnvironmentNamesToClear) {
        if ($SavedEnvironment.ContainsKey($Name)) {
            Set-Item -LiteralPath "Env:$Name" -Value $SavedEnvironment[$Name]
        }
        else {
            Remove-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue
        }
    }
}

Write-Output "Verification root: $RunRoot"
