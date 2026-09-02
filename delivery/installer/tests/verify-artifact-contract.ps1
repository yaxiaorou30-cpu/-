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
        if ([IO.Path]::GetFileName([string]$Artifact.fileName) -ne [string]$Artifact.fileName) {
            throw "$Label.fileName must be a plain file name."
        }
        if (
            $Artifact.PSObject.Properties.Name -notcontains "size" -or
            [long]$Artifact.size -le 0
        ) {
            throw "$Label.size must be greater than zero when ready."
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

function Assert-NoLocalOrProtectedPath {
    param(
        $Value,
        [string]$JsonPath = "$"
    )

    if ($null -eq $Value) {
        return
    }

    if ($Value -is [string]) {
        $Text = [string]$Value
        $ParsedUri = $null
        if (
            [uri]::TryCreate($Text, [UriKind]::Absolute, [ref]$ParsedUri) -and
            $ParsedUri.Scheme -in @("http", "https")
        ) {
            return
        }
        if (
            $Text -match "(?i)^file://" -or
            [IO.Path]::IsPathRooted($Text) -or
            $Text -match "(?i)(^|[\\/])(?:\.codex_tmp|requirements|data)(?:[\\/]|$)"
        ) {
            throw "runtime-manifest.json contains a local or protected source path at $JsonPath."
        }
        return
    }

    if ($Value -is [Management.Automation.PSCustomObject]) {
        foreach ($Property in $Value.PSObject.Properties) {
            Assert-NoLocalOrProtectedPath $Property.Value "$JsonPath.$($Property.Name)"
        }
        return
    }

    if ($Value -is [Collections.IEnumerable]) {
        $Index = 0
        foreach ($Item in $Value) {
            Assert-NoLocalOrProtectedPath $Item "$JsonPath[$Index]"
            $Index++
        }
    }
}

if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
    throw "Missing runtime manifest: $ManifestPath"
}

$RawManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $ManifestPath
$Manifest = $RawManifest | ConvertFrom-Json
Assert-NoLocalOrProtectedPath $Manifest
$ManifestRoot = Split-Path -Parent ([IO.Path]::GetFullPath($ManifestPath))
$AllowedLockRoot = [IO.Path]::GetFullPath((Join-Path $ManifestRoot "..\locks\generated"))
$AllowedLockPrefix = $AllowedLockRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$AllowedBuildInputRoot = [IO.Path]::GetFullPath((Join-Path $ManifestRoot "build-inputs"))
$AllowedBuildInputPrefix = $AllowedBuildInputRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$AllowedBuildLockRoot = [IO.Path]::GetFullPath((Join-Path $ManifestRoot "build-locks"))
$AllowedBuildLockPrefix = $AllowedBuildLockRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar

Assert-Equal $Manifest.schemaVersion 1 "schemaVersion"
Assert-Equal $Manifest.target.platform "windows-11-x64" "target.platform"
Assert-Equal $Manifest.target.python "cpython-3.13.9-x64" "target.python"
Assert-Equal $Manifest.installPolicy.networkAllowed $true "installPolicy.networkAllowed"
Assert-Equal $Manifest.installPolicy.endUserBuildAllowed $false "installPolicy.endUserBuildAllowed"
Assert-Equal $Manifest.installPolicy.requireHashes $true "installPolicy.requireHashes"
Assert-Equal $Manifest.installPolicy.onlyBinary $true "installPolicy.onlyBinary"

Assert-Equal $Manifest.wheelBuild.python "cpython-3.13.9-x64" "wheelBuild.python"
Assert-Equal $Manifest.wheelBuild.uv "0.10.8" "wheelBuild.uv"
Assert-Equal $Manifest.wheelBuild.sourceDateEpoch 1788019199 "wheelBuild.sourceDateEpoch"
Assert-Equal $Manifest.wheelBuild.runsPerArtifact 2 "wheelBuild.runsPerArtifact"
Assert-Equal $Manifest.wheelBuild.networkDuringTargetBuild $false "wheelBuild.networkDuringTargetBuild"
Assert-Equal (@($Manifest.wheelBuild.selectedArtifactIds) -join "|") "jieba-0.42.1|qrcode-terminal-0.8" "wheelBuild.selectedArtifactIds"
Assert-Equal (@($Manifest.wheelBuild.validationOnlyArtifactIds) -join "|") "bilibili-api-python-17.4.2" "wheelBuild.validationOnlyArtifactIds"
Assert-Equal $Manifest.wheelBuild.dependencyInstall.requireHashes $true "wheelBuild.dependencyInstall.requireHashes"
Assert-Equal $Manifest.wheelBuild.dependencyInstall.onlyBinary $true "wheelBuild.dependencyInstall.onlyBinary"

$BuildInputPath = [IO.Path]::GetFullPath((Join-Path $ManifestRoot ([string]$Manifest.wheelBuild.input.path)))
if (-not $BuildInputPath.StartsWith($AllowedBuildInputPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "wheelBuild.input.path escapes the build-inputs directory."
}
if (-not (Test-Path -LiteralPath $BuildInputPath -PathType Leaf)) {
    throw "wheelBuild.input.path does not exist."
}
Assert-Equal $Manifest.wheelBuild.input.sha256 "d81a0bb625ea04dd183867f8193568633db73d37a94fd92b0bd8cb0db8f8d694" "wheelBuild.input.sha256"
$ActualBuildInputHash = (Get-FileHash -LiteralPath $BuildInputPath -Algorithm SHA256).Hash.ToLowerInvariant()
Assert-Equal $ActualBuildInputHash $Manifest.wheelBuild.input.sha256 "wheelBuild.input.fileHash"

$BuildLockPath = [IO.Path]::GetFullPath((Join-Path $ManifestRoot ([string]$Manifest.wheelBuild.dependencyLock.path)))
if (-not $BuildLockPath.StartsWith($AllowedBuildLockPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "wheelBuild.dependencyLock.path escapes the build-locks directory."
}
if (-not (Test-Path -LiteralPath $BuildLockPath -PathType Leaf)) {
    throw "wheelBuild.dependencyLock.path does not exist."
}
Assert-Equal $Manifest.wheelBuild.dependencyLock.sha256 "ab9bb7dadd6e17eb89ed9b1a8b124da64009028fa7589c0f55e15f404c5e6598" "wheelBuild.dependencyLock.sha256"
$ActualBuildLockHash = (Get-FileHash -LiteralPath $BuildLockPath -Algorithm SHA256).Hash.ToLowerInvariant()
Assert-Equal $ActualBuildLockHash $Manifest.wheelBuild.dependencyLock.sha256 "wheelBuild.dependencyLock.fileHash"

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
$ExpectedReadyWheels = @{
    "jieba-0.42.1" = @{
        sourceType = "pypi-sdist"
        sourceFileName = "jieba-0.42.1.tar.gz"
        sourceSize = 19214172
        sourceSha256 = "055ca12f62674fafed09427f176506079bc135638a14e23e25be909131928db2"
        sourceUrl = "https://files.pythonhosted.org/packages/c6/cb/18eeb235f833b726522d7ebed54f2278ce28ba9438e3135ab0278d9792a2/jieba-0.42.1.tar.gz"
        fileName = "jieba-0.42.1-py3-none-any.whl"
        size = 19314527
        sha256 = "6db280488a8989695b450928a302fd81a6e35a46449fd58c54f2ff5ae06ce866"
    }
    "qrcode-terminal-0.8" = @{
        sourceType = "pypi-sdist"
        sourceFileName = "qrcode-terminal-0.8.tar.gz"
        sourceSize = 1666
        sourceSha256 = "1e2b69e662b9346e98dd95983033e9d43cff0643d8afda12605f515428e666c0"
        sourceUrl = "https://files.pythonhosted.org/packages/96/62/2422c088b7219db9f78c912418254db9896d1b20ab15e83aae2821419a65/qrcode-terminal-0.8.tar.gz"
        fileName = "qrcode_terminal-0.8-py3-none-any.whl"
        size = 2661
        sha256 = "8cd9b4e146051633b39b734d692c2f1cf4d6d85e0694e093546416c63aca2714"
    }
    "bilibili-api-python-17.4.2" = @{
        sourceType = "pypi-wheel"
        url = "https://files.pythonhosted.org/packages/8e/41/c12f4c52cecd6ca6c4bee49a8949ed3df3561e5dd12b891aba96dcdc4502/bilibili_api_python-17.4.2-py3-none-any.whl"
        fileName = "bilibili_api_python-17.4.2-py3-none-any.whl"
        size = 387324
        sha256 = "91e002b2e0bcd3eb50239e35ceb849133b574f407a92a06636e1de1031b6d09d"
    }
}
$ExpectedPendingWheels = @{
    "bilibili-cli-0.6.2" = @{
        status = "pending-d2-build"
        sourceType = "git-commit"
        sourceCommit = "dbe28551930df43b633baa52e9639832aeada967"
    }
    "newspaper4k-0.9.6" = @{
        status = "pending-d2-build"
        sourceType = "git-commit"
        sourceCommit = "b53a81fc01ff54601faaeae68d6b4a6d2f18efcb"
    }
    "aiotieba-4.7.2a8" = @{
        status = "pending-d2-build"
        sourceType = "git-commit"
        sourceCommit = "bae68256fd250d5178e1447899ffa155c77eda38"
        requiresBuildToolchain = $true
    }
}
Assert-Equal @($Manifest.wheelArtifacts).Count $ExpectedWheelIds.Count "wheelArtifacts.Count"
$ActualWheelIds = @($Manifest.wheelArtifacts | ForEach-Object { $_.id } | Sort-Object -Unique)
Assert-Equal $ActualWheelIds.Count $ExpectedWheelIds.Count "wheelArtifacts.UniqueCount"

$UnapprovedDistributionGateCount = @(
    $Manifest.wheelArtifacts |
        Where-Object {
            $_.PSObject.Properties.Name -contains "distributionGate" -and
            [string]$_.distributionGate -ne "approved-d4-license-review"
        }
).Count
if ($Mode -eq "ReleaseReady" -and $UnapprovedDistributionGateCount -gt 0) {
    throw "$UnapprovedDistributionGateCount distribution gate(s) are not approved."
}

foreach ($Wheel in @($Manifest.wheelArtifacts)) {
    if ($Wheel.id -notin $ExpectedWheelIds) {
        throw "Unexpected wheel artifact: $($Wheel.id)."
    }
    Assert-ArtifactState $Wheel "wheelArtifacts.$($Wheel.id)"
    if ($Wheel.status -eq "ready" -and -not $ExpectedReadyWheels.ContainsKey([string]$Wheel.id)) {
        throw "wheelArtifacts.$($Wheel.id) is ready without a pinned approved contract."
    }
    if ($ExpectedReadyWheels.ContainsKey([string]$Wheel.id)) {
        $ExpectedWheel = $ExpectedReadyWheels[[string]$Wheel.id]
        Assert-Equal $Wheel.status "ready" "wheelArtifacts.$($Wheel.id).status"
        Assert-Equal $Wheel.sourceType $ExpectedWheel.sourceType "wheelArtifacts.$($Wheel.id).sourceType"
        Assert-Equal $Wheel.fileName $ExpectedWheel.fileName "wheelArtifacts.$($Wheel.id).fileName"
        Assert-Equal $Wheel.size $ExpectedWheel.size "wheelArtifacts.$($Wheel.id).size"
        Assert-Equal $Wheel.sha256 $ExpectedWheel.sha256 "wheelArtifacts.$($Wheel.id).sha256"
        Assert-Equal $Wheel.tag "py3-none-any" "wheelArtifacts.$($Wheel.id).tag"
        if ($ExpectedWheel.sourceType -eq "pypi-sdist") {
            Assert-Equal $Wheel.sourceFileName $ExpectedWheel.sourceFileName "wheelArtifacts.$($Wheel.id).sourceFileName"
            Assert-Equal $Wheel.sourceSize $ExpectedWheel.sourceSize "wheelArtifacts.$($Wheel.id).sourceSize"
            Assert-Equal $Wheel.sourceSha256 $ExpectedWheel.sourceSha256 "wheelArtifacts.$($Wheel.id).sourceSha256"
            Assert-Equal $Wheel.sourceUrl $ExpectedWheel.sourceUrl "wheelArtifacts.$($Wheel.id).sourceUrl"
            Assert-Equal $Wheel.sameHostRepeatable $true "wheelArtifacts.$($Wheel.id).sameHostRepeatable"
        }
        else {
            Assert-Equal $Wheel.url $ExpectedWheel.url "wheelArtifacts.$($Wheel.id).url"
            Assert-Equal $Wheel.upstreamPublished $true "wheelArtifacts.$($Wheel.id).upstreamPublished"
            Assert-Equal $Wheel.recordValidated $true "wheelArtifacts.$($Wheel.id).recordValidated"
        }
    }
    elseif ($ExpectedPendingWheels.ContainsKey([string]$Wheel.id)) {
        $ExpectedWheel = $ExpectedPendingWheels[[string]$Wheel.id]
        Assert-Equal $Wheel.status $ExpectedWheel.status "wheelArtifacts.$($Wheel.id).status"
        Assert-Equal $Wheel.sourceType $ExpectedWheel.sourceType "wheelArtifacts.$($Wheel.id).sourceType"
        Assert-Equal $Wheel.sourceCommit $ExpectedWheel.sourceCommit "wheelArtifacts.$($Wheel.id).sourceCommit"
        Assert-Equal $Wheel.fileName $null "wheelArtifacts.$($Wheel.id).fileName"
        Assert-Equal $Wheel.sha256 $null "wheelArtifacts.$($Wheel.id).sha256"
        if ($ExpectedWheel.ContainsKey("requiresBuildToolchain")) {
            Assert-Equal $Wheel.requiresBuildToolchain $ExpectedWheel.requiresBuildToolchain "wheelArtifacts.$($Wheel.id).requiresBuildToolchain"
        }
    }
    else {
        throw "wheelArtifacts.$($Wheel.id) has no expected contract."
    }
    if ($Wheel.id -eq "bilibili-api-python-17.4.2") {
        Assert-Equal $Wheel.license "GPL-3.0-or-later" "wheelArtifacts.bilibili-api-python.license"
        if ($Wheel.distributionGate -notin @("pending-d4-license-review", "approved-d4-license-review")) {
            throw "wheelArtifacts.bilibili-api-python.distributionGate has an unsupported value."
        }
    }
}

$ExpectedBrowserIds = @(
    "chromium-1228-win64",
    "chromium-headless-shell-1228-win64",
    "chromium-1234-win64",
    "chromium-headless-shell-1234-win64",
    "ffmpeg-1011-win64",
    "winldd-1007-win64"
)
$ExpectedBrowsers = @{
    "chromium-1228-win64" = @{
        status = "pending-d2-download-hash"
        revision = "1228"
        browserVersion = "149.0.7827.55"
        upstreamFileName = "chrome-win64.zip"
        fileName = "playwright-chromium-1228-win64.zip"
        url = "https://cdn.playwright.dev/builds/cft/149.0.7827.55/win64/chrome-win64.zip"
    }
    "chromium-headless-shell-1228-win64" = @{
        status = "pending-d2-download-hash"
        revision = "1228"
        browserVersion = "149.0.7827.55"
        upstreamFileName = "chrome-headless-shell-win64.zip"
        fileName = "playwright-chromium-headless-shell-1228-win64.zip"
        url = "https://cdn.playwright.dev/builds/cft/149.0.7827.55/win64/chrome-headless-shell-win64.zip"
    }
    "chromium-1234-win64" = @{
        status = "pending-d2-download-hash"
        revision = "1234"
        browserVersion = "151.0.7922.34"
        upstreamFileName = "chrome-win64.zip"
        fileName = "playwright-chromium-1234-win64.zip"
        url = "https://cdn.playwright.dev/builds/cft/151.0.7922.34/win64/chrome-win64.zip"
    }
    "chromium-headless-shell-1234-win64" = @{
        status = "pending-d2-download-hash"
        revision = "1234"
        browserVersion = "151.0.7922.34"
        upstreamFileName = "chrome-headless-shell-win64.zip"
        fileName = "playwright-chromium-headless-shell-1234-win64.zip"
        url = "https://cdn.playwright.dev/builds/cft/151.0.7922.34/win64/chrome-headless-shell-win64.zip"
    }
    "ffmpeg-1011-win64" = @{
        status = "pending-d2-download-hash"
        revision = "1011"
        browserVersion = $null
        upstreamFileName = "ffmpeg-win64.zip"
        fileName = "playwright-ffmpeg-1011-win64.zip"
        url = "https://cdn.playwright.dev/dbazure/download/playwright/builds/ffmpeg/1011/ffmpeg-win64.zip"
    }
    "winldd-1007-win64" = @{
        status = "pending-d2-download-hash"
        revision = "1007"
        browserVersion = $null
        upstreamFileName = "winldd-win64.zip"
        fileName = "playwright-winldd-1007-win64.zip"
        url = "https://cdn.playwright.dev/dbazure/download/playwright/builds/winldd/1007/winldd-win64.zip"
    }
}
$ExpectedReadyBrowsers = @{}
Assert-Equal @($Manifest.browserArtifacts).Count $ExpectedBrowserIds.Count "browserArtifacts.Count"
$ActualBrowserIds = @($Manifest.browserArtifacts | ForEach-Object { $_.id } | Sort-Object -Unique)
Assert-Equal $ActualBrowserIds.Count $ExpectedBrowserIds.Count "browserArtifacts.UniqueCount"
foreach ($Browser in @($Manifest.browserArtifacts)) {
    if ($Browser.id -notin $ExpectedBrowserIds) {
        throw "Unexpected browser artifact: $($Browser.id)."
    }
    Assert-ArtifactState $Browser "browserArtifacts.$($Browser.id)"
    if ($Browser.status -eq "ready" -and -not $ExpectedReadyBrowsers.ContainsKey([string]$Browser.id)) {
        throw "browserArtifacts.$($Browser.id) is ready without a pinned approved contract."
    }
    $ExpectedBrowser = $ExpectedBrowsers[[string]$Browser.id]
    Assert-Equal $Browser.status $ExpectedBrowser.status "browserArtifacts.$($Browser.id).status"
    Assert-Equal $Browser.revision $ExpectedBrowser.revision "browserArtifacts.$($Browser.id).revision"
    Assert-Equal $Browser.browserVersion $ExpectedBrowser.browserVersion "browserArtifacts.$($Browser.id).browserVersion"
    Assert-Equal $Browser.upstreamFileName $ExpectedBrowser.upstreamFileName "browserArtifacts.$($Browser.id).upstreamFileName"
    Assert-Equal $Browser.fileName $ExpectedBrowser.fileName "browserArtifacts.$($Browser.id).fileName"
    Assert-Equal $Browser.url $ExpectedBrowser.url "browserArtifacts.$($Browser.id).url"
    if ($ExpectedReadyBrowsers.ContainsKey([string]$Browser.id)) {
        $ExpectedReadyBrowser = $ExpectedReadyBrowsers[[string]$Browser.id]
        Assert-Equal $Browser.size $ExpectedReadyBrowser.size "browserArtifacts.$($Browser.id).size"
        Assert-Equal $Browser.sha256 $ExpectedReadyBrowser.sha256 "browserArtifacts.$($Browser.id).sha256"
    }
    else {
        Assert-Equal $Browser.sha256 $null "browserArtifacts.$($Browser.id).sha256"
    }
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
    Assert-Equal $Tool.status "ready" "toolArtifacts.$($Tool.id).status"
    switch ($Tool.id) {
        "python-runtime-archive" {
            Assert-Equal $Tool.version "cpython-3.13.9-x64" "toolArtifacts.python.version"
            Assert-Equal $Tool.url "https://github.com/astral-sh/python-build-standalone/releases/download/20251120/cpython-3.13.9%2B20251120-x86_64-pc-windows-msvc-install_only_stripped.tar.gz" "toolArtifacts.python.url"
            Assert-Equal $Tool.fileName "cpython-3.13.9+20251120-x86_64-pc-windows-msvc-install_only_stripped.tar.gz" "toolArtifacts.python.fileName"
            Assert-Equal $Tool.size 21638637 "toolArtifacts.python.size"
            Assert-Equal $Tool.sha256 "f4c22b31ddbf8d7824cbcba2d8707621c2c8fab1fb6d2c1810c2bb0304d8e9a8" "toolArtifacts.python.sha256"
            Assert-Equal $Tool.executableSha256 "30557F6B49FC4B6574CA3EF91EDB8D148CFC989DD75C846F5639B76DB800E7E2" "toolArtifacts.python.executableSha256"
        }
        "uv-runtime-archive" {
            Assert-Equal $Tool.version "0.10.8" "toolArtifacts.uv.version"
            Assert-Equal $Tool.url "https://github.com/astral-sh/uv/releases/download/0.10.8/uv-x86_64-pc-windows-msvc.zip" "toolArtifacts.uv.url"
            Assert-Equal $Tool.fileName "uv-x86_64-pc-windows-msvc.zip" "toolArtifacts.uv.fileName"
            Assert-Equal $Tool.size 22159808 "toolArtifacts.uv.size"
            Assert-Equal $Tool.sha256 "2e70ecd22196cbd9d14eefb700814bcafc5b75a0d8275b52e8402e5fe256d928" "toolArtifacts.uv.sha256"
            Assert-Equal $Tool.expectedExecutableSha256 "067CF5D81A2DC006C1C76FA160B4DA96A35BC80900C22FAED7ACFC52510FCDF5" "toolArtifacts.uv.executableSha256"
        }
        "inno-setup-builder" {
            Assert-Equal $Tool.version "7.1.0-x64" "toolArtifacts.inno.version"
            Assert-Equal $Tool.url "https://github.com/jrsoftware/issrc/releases/download/is-7_1_0/innosetup-7.1.0-x64.exe" "toolArtifacts.inno.url"
            Assert-Equal $Tool.fileName "innosetup-7.1.0-x64.exe" "toolArtifacts.inno.fileName"
            Assert-Equal $Tool.size 14304168 "toolArtifacts.inno.size"
            Assert-Equal $Tool.sha256 "0362a383ed217d4c4239b5933866dd96d3eb2102737da92f80f6057a4b40df2f" "toolArtifacts.inno.sha256"
            Assert-Equal $Tool.authenticodeSigner "Pyrsys B.V." "toolArtifacts.inno.authenticodeSigner"
            Assert-Equal $Tool.authenticodeThumbprint "E0AB19C8D38CBF9C44709925122A7A02F8C70CB7" "toolArtifacts.inno.authenticodeThumbprint"
        }
    }
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
Write-Output "UNAPPROVED_DISTRIBUTION_GATES=$UnapprovedDistributionGateCount"
Write-Output "NETWORK_ACTIONS=0"
Write-Output "FILESYSTEM_MUTATIONS=0"
