[CmdletBinding()]
param(
    [ValidateSet("PlanOnly", "ReleaseReady")]
    [string]$Mode = "PlanOnly",

    [string]$ManifestPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
    $ManifestPath = Join-Path $PSScriptRoot "..\runtime-manifest.json"
}

function Assert-Equal {
    param($Actual, $Expected, [string]$Label)
    if ($Actual -ne $Expected) {
        throw "$Label must be '$Expected'; got '$Actual'."
    }
}

function Assert-Sha256 {
    param($Actual, [string]$Label)
    if ([string]$Actual -notmatch "^[0-9A-Fa-f]{64}$") {
        throw "$Label must be a SHA256 value."
    }
}

function Assert-ArtifactState {
    param($Artifact, [string]$Label)

    if ($Artifact.status -eq "ready") {
        if ([string]::IsNullOrWhiteSpace([string]$Artifact.fileName)) {
            throw "$Label.fileName is required when ready."
        }
        Assert-Sha256 $Artifact.sha256 "$Label.sha256"
        if ($Artifact.PSObject.Properties.Name -contains "url") {
            if ([string]::IsNullOrWhiteSpace([string]$Artifact.url)) {
                throw "$Label.url is required when ready."
            }
            $ParsedUri = $null
            if (-not [uri]::TryCreate([string]$Artifact.url, [UriKind]::Absolute, [ref]$ParsedUri)) {
                throw "$Label.url must be an absolute URI."
            }
            if ($ParsedUri.Scheme -ne "https") {
                throw "$Label.url must use HTTPS."
            }
        }
        return
    }

    if ($Artifact.status -notlike "pending-*") {
        throw "$Label has unsupported status '$($Artifact.status)'."
    }
    if ($Mode -eq "ReleaseReady") {
        throw "$Label is not release ready: $($Artifact.status)."
    }
}

if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
    throw "Missing runtime manifest: $ManifestPath"
}

$RawManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $ManifestPath
if ($RawManifest -match "(?i)([A-Z]:\\|file://|\.codex_tmp|requirements/|data/)") {
    throw "runtime-manifest.json contains a local or protected source path."
}
$Manifest = $RawManifest | ConvertFrom-Json
$ManifestRoot = Split-Path -Parent ([IO.Path]::GetFullPath($ManifestPath))
$AllowedLockRoot = [IO.Path]::GetFullPath((Join-Path $ManifestRoot "..\locks\generated"))
$AllowedLockPrefix = $AllowedLockRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar

Assert-Equal $Manifest.schemaVersion 1 "schemaVersion"
Assert-Equal $Manifest.target.platform "windows-11-x64" "target.platform"
Assert-Equal $Manifest.target.python "cpython-3.13.9-x64" "target.python"
Assert-Equal $Manifest.installPolicy.networkAllowed $true "installPolicy.networkAllowed"
Assert-Equal $Manifest.installPolicy.endUserBuildAllowed $false "installPolicy.endUserBuildAllowed"
Assert-Equal $Manifest.installPolicy.requireHashes $true "installPolicy.requireHashes"
Assert-Equal $Manifest.installPolicy.onlyBinary $true "installPolicy.onlyBinary"

$ExpectedLocks = @{
    "main" = "6563e6bffab7b96a7f4a3dd538626aa691af0a34c649eabe3041980b6e536d6f"
    "test" = "7c794c8f11dccb06645c6c29be0a4bda0dcac0fe0bade767bd5011193fdc50f3"
    "scrapling" = "63b8ece936586663d224c959b6a41efdbd5f1f5a592e439dbbf3853cbf628480"
    "bilibili-cli-runtime" = "3011e71d1d4e6e80fa979526806907a6937c7f89dfd47ee16675f481a818e079"
    "newspaper4k-runtime" = "176e8d005c8310df02cdb9b3c179c71a4ceae807d6d3367d0711bfabe3121a6a"
    "aiotieba-runtime" = "dfbcc13c5bc6e109bd399b110da3d3715211494d5466bf414f24ad419b961d43"
}
Assert-Equal @($Manifest.dependencyLocks).Count $ExpectedLocks.Count "dependencyLocks.Count"
foreach ($Lock in @($Manifest.dependencyLocks)) {
    if (-not $ExpectedLocks.ContainsKey([string]$Lock.id)) {
        throw "Unexpected dependency lock: $($Lock.id)."
    }
    Assert-Equal $Lock.sha256 $ExpectedLocks[[string]$Lock.id] "dependencyLocks.$($Lock.id).sha256"
    $LockPath = [IO.Path]::GetFullPath((Join-Path $ManifestRoot ([string]$Lock.path)))
    if (-not $LockPath.StartsWith($AllowedLockPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "dependencyLocks.$($Lock.id).path escapes the generated lock directory."
    }
    if (-not (Test-Path -LiteralPath $LockPath -PathType Leaf)) {
        throw "dependencyLocks.$($Lock.id).path does not exist."
    }
    $ActualLockHash = (Get-FileHash -LiteralPath $LockPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Assert-Equal $ActualLockHash $Lock.sha256 "dependencyLocks.$($Lock.id).fileHash"
    if ($Lock.id -eq "test") {
        Assert-Equal $Lock.installToEndUser $false "dependencyLocks.test.installToEndUser"
    }
    else {
        Assert-Equal $Lock.installToEndUser $true "dependencyLocks.$($Lock.id).installToEndUser"
    }
}

$ExpectedWheelIds = @(
    "jieba-0.42.1",
    "qrcode-terminal-0.8",
    "bilibili-api-python-17.4.2",
    "bilibili-cli-0.6.2",
    "newspaper4k-0.9.6",
    "aiotieba-4.7.2a8"
)
Assert-Equal @($Manifest.wheelArtifacts).Count $ExpectedWheelIds.Count "wheelArtifacts.Count"
$ActualWheelIds = @($Manifest.wheelArtifacts | ForEach-Object { $_.id } | Sort-Object -Unique)
Assert-Equal $ActualWheelIds.Count $ExpectedWheelIds.Count "wheelArtifacts.UniqueCount"
foreach ($Wheel in @($Manifest.wheelArtifacts)) {
    if ($Wheel.id -notin $ExpectedWheelIds) {
        throw "Unexpected wheel artifact: $($Wheel.id)."
    }
    Assert-ArtifactState $Wheel "wheelArtifacts.$($Wheel.id)"
}

$ExpectedBrowserIds = @(
    "chromium-1228-win64",
    "chromium-headless-shell-1228-win64",
    "chromium-1234-win64",
    "chromium-headless-shell-1234-win64",
    "ffmpeg-1011-win64"
)
Assert-Equal @($Manifest.browserArtifacts).Count $ExpectedBrowserIds.Count "browserArtifacts.Count"
$ActualBrowserIds = @($Manifest.browserArtifacts | ForEach-Object { $_.id } | Sort-Object -Unique)
Assert-Equal $ActualBrowserIds.Count $ExpectedBrowserIds.Count "browserArtifacts.UniqueCount"
foreach ($Browser in @($Manifest.browserArtifacts)) {
    if ($Browser.id -notin $ExpectedBrowserIds) {
        throw "Unexpected browser artifact: $($Browser.id)."
    }
    Assert-ArtifactState $Browser "browserArtifacts.$($Browser.id)"
}

$ExpectedToolIds = @("python-runtime-archive", "uv-runtime-archive", "inno-setup-builder")
Assert-Equal @($Manifest.toolArtifacts).Count $ExpectedToolIds.Count "toolArtifacts.Count"
$ActualToolIds = @($Manifest.toolArtifacts | ForEach-Object { $_.id } | Sort-Object -Unique)
Assert-Equal $ActualToolIds.Count $ExpectedToolIds.Count "toolArtifacts.UniqueCount"
foreach ($Tool in @($Manifest.toolArtifacts)) {
    if ($Tool.id -notin $ExpectedToolIds) {
        throw "Unexpected tool artifact: $($Tool.id)."
    }
    Assert-ArtifactState $Tool "toolArtifacts.$($Tool.id)"
}

$PendingCount = @(
    @($Manifest.wheelArtifacts) +
    @($Manifest.browserArtifacts) +
    @($Manifest.toolArtifacts) |
        Where-Object { $_.status -ne "ready" }
).Count

Write-Output "ARTIFACT_CONTRACT=PASS"
Write-Output "MODE=$Mode"
Write-Output "PENDING_ARTIFACTS=$PendingCount"
Write-Output "NETWORK_ACTIONS=0"
Write-Output "FILESYSTEM_MUTATIONS=0"
