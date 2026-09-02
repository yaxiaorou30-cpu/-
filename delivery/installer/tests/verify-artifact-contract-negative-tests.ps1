[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ContractScript = Join-Path $PSScriptRoot "verify-artifact-contract.ps1"
$InstallerRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$SourceManifest = Join-Path $InstallerRoot "runtime-manifest.json"
$PowerShellPath = (Get-Command powershell.exe -ErrorAction Stop | Select-Object -First 1).Source
$FixturePaths = [Collections.Generic.List[string]]::new()
$Utf8NoBom = New-Object Text.UTF8Encoding($false)

function Invoke-Contract {
    param(
        [string]$Mode,
        [string]$ManifestPath
    )

    $PreviousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $Output = & $PowerShellPath `
            -NoProfile `
            -ExecutionPolicy Bypass `
            -File $ContractScript `
            -Mode $Mode `
            -ManifestPath $ManifestPath 2>&1
        $ExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }

    return [pscustomobject]@{
        ExitCode = $ExitCode
        Output = ($Output | Out-String)
    }
}

function Assert-Succeeded {
    param($Result, [string]$Label)
    if ($Result.ExitCode -ne 0) {
        throw "$Label unexpectedly failed:`n$($Result.Output)"
    }
}

function Assert-FailedWith {
    param($Result, [string]$Pattern, [string]$Label)
    if ($Result.ExitCode -eq 0) {
        throw "$Label unexpectedly succeeded."
    }
    if ($Result.Output -notmatch $Pattern) {
        throw "$Label failed for the wrong reason:`n$($Result.Output)"
    }
}

function New-FixturePath {
    $Path = Join-Path $InstallerRoot (".artifact-contract-negative-{0}.json" -f [guid]::NewGuid().ToString("N"))
    $FixturePaths.Add($Path)
    return $Path
}

function Write-Fixture {
    param($Manifest, [string]$Path)
    $Json = $Manifest | ConvertTo-Json -Depth 100
    [IO.File]::WriteAllText($Path, $Json, $Utf8NoBom)
}

try {
    $Baseline = Invoke-Contract -Mode "PlanOnly" -ManifestPath $SourceManifest
    Assert-Succeeded $Baseline "Baseline PlanOnly contract"

    $HttpsPathManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $SourceManifest | ConvertFrom-Json
    $HttpsPathManifest | Add-Member -NotePropertyName "positiveTestDataUrl" -NotePropertyValue "https://example.com/data/artifact.zip"
    $HttpsPathManifest | Add-Member -NotePropertyName "positiveTestRequirementsUrl" -NotePropertyValue "https://example.com/requirements/artifact.whl"
    $HttpsPathFixture = New-FixturePath
    Write-Fixture $HttpsPathManifest $HttpsPathFixture
    $HttpsPathResult = Invoke-Contract -Mode "PlanOnly" -ManifestPath $HttpsPathFixture
    Assert-Succeeded $HttpsPathResult "HTTPS path segment check"

    $ProtectedPathManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $SourceManifest | ConvertFrom-Json
    $ProtectedPathManifest | Add-Member -NotePropertyName "negativeTestSource" -NotePropertyValue "requirements\secret.txt"
    $ProtectedPathFixture = New-FixturePath
    Write-Fixture $ProtectedPathManifest $ProtectedPathFixture
    $ProtectedPathResult = Invoke-Contract -Mode "PlanOnly" -ManifestPath $ProtectedPathFixture
    Assert-FailedWith $ProtectedPathResult "contains a local or protected source path" "Protected Windows path check"

    $DataPathManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $SourceManifest | ConvertFrom-Json
    $DataPathManifest | Add-Member -NotePropertyName "negativeTestSource" -NotePropertyValue "data\local.sqlite"
    $DataPathFixture = New-FixturePath
    Write-Fixture $DataPathManifest $DataPathFixture
    $DataPathResult = Invoke-Contract -Mode "PlanOnly" -ManifestPath $DataPathFixture
    Assert-FailedWith $DataPathResult "contains a local or protected source path" "Protected data path check"

    $DrivePathManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $SourceManifest | ConvertFrom-Json
    $DrivePathManifest | Add-Member -NotePropertyName "negativeTestSource" -NotePropertyValue "C:\temp\artifact.whl"
    $DrivePathFixture = New-FixturePath
    Write-Fixture $DrivePathManifest $DrivePathFixture
    $DrivePathResult = Invoke-Contract -Mode "PlanOnly" -ManifestPath $DrivePathFixture
    Assert-FailedWith $DrivePathResult "contains a local or protected source path" "Absolute drive path check"

    $UncPathManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $SourceManifest | ConvertFrom-Json
    $UncPathManifest | Add-Member -NotePropertyName "negativeTestSource" -NotePropertyValue "\\server\share\artifact.whl"
    $UncPathFixture = New-FixturePath
    Write-Fixture $UncPathManifest $UncPathFixture
    $UncPathResult = Invoke-Contract -Mode "PlanOnly" -ManifestPath $UncPathFixture
    Assert-FailedWith $UncPathResult "contains a local or protected source path" "UNC path check"

    $ForwardUncPathManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $SourceManifest | ConvertFrom-Json
    $ForwardUncPathManifest | Add-Member -NotePropertyName "negativeTestSource" -NotePropertyValue "//server/share/artifact.whl"
    $ForwardUncPathFixture = New-FixturePath
    Write-Fixture $ForwardUncPathManifest $ForwardUncPathFixture
    $ForwardUncPathResult = Invoke-Contract -Mode "PlanOnly" -ManifestPath $ForwardUncPathFixture
    Assert-FailedWith $ForwardUncPathResult "contains a local or protected source path" "Forward-slash UNC path check"

    $UnapprovedReadyManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $SourceManifest | ConvertFrom-Json
    $FutureWheel = @($UnapprovedReadyManifest.wheelArtifacts | Where-Object { $_.id -eq "bilibili-cli-0.6.2" })[0]
    $FutureWheel.status = "ready"
    $FutureWheel.fileName = "bilibili_cli-0.6.2-py3-none-any.whl"
    $FutureWheel.sha256 = "0" * 64
    $FutureWheel | Add-Member -NotePropertyName "size" -NotePropertyValue 1
    $UnapprovedReadyFixture = New-FixturePath
    Write-Fixture $UnapprovedReadyManifest $UnapprovedReadyFixture
    $UnapprovedReadyResult = Invoke-Contract -Mode "PlanOnly" -ManifestPath $UnapprovedReadyFixture
    Assert-FailedWith $UnapprovedReadyResult "ready without a pinned approved contract" "Unapproved ready artifact check"

    $UnapprovedBrowserManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $SourceManifest | ConvertFrom-Json
    $FutureBrowser = @($UnapprovedBrowserManifest.browserArtifacts | Where-Object { $_.id -eq "chromium-1228-win64" })[0]
    $FutureBrowser.sha256 = "0" * 64
    $FutureBrowser.size = 1
    $UnapprovedBrowserFixture = New-FixturePath
    Write-Fixture $UnapprovedBrowserManifest $UnapprovedBrowserFixture
    $UnapprovedBrowserResult = Invoke-Contract -Mode "PlanOnly" -ManifestPath $UnapprovedBrowserFixture
    Assert-FailedWith $UnapprovedBrowserResult "size must be '192511857'" "Forged ready browser check"

    $ForgedBrowserHashManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $SourceManifest | ConvertFrom-Json
    $ForgedBrowserHash = @($ForgedBrowserHashManifest.browserArtifacts | Where-Object { $_.id -eq "chromium-1228-win64" })[0]
    $ForgedBrowserHash.sha256 = "0" * 64
    $ForgedBrowserHashFixture = New-FixturePath
    Write-Fixture $ForgedBrowserHashManifest $ForgedBrowserHashFixture
    $ForgedBrowserHashResult = Invoke-Contract -Mode "PlanOnly" -ManifestPath $ForgedBrowserHashFixture
    Assert-FailedWith $ForgedBrowserHashResult "sha256 must be" "Forged ready browser SHA256 check"

    $UnexpectedPendingManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $SourceManifest | ConvertFrom-Json
    $PendingWheel = @($UnexpectedPendingManifest.wheelArtifacts | Where-Object { $_.id -eq "newspaper4k-0.9.6" })[0]
    $PendingWheel.status = "pending-unreviewed-state"
    $UnexpectedPendingFixture = New-FixturePath
    Write-Fixture $UnexpectedPendingManifest $UnexpectedPendingFixture
    $UnexpectedPendingResult = Invoke-Contract -Mode "PlanOnly" -ManifestPath $UnexpectedPendingFixture
    Assert-FailedWith $UnexpectedPendingResult "status must be 'pending-d2-build'" "Unexpected pending state check"

    $ReleaseReadyResult = Invoke-Contract -Mode "ReleaseReady" -ManifestPath $SourceManifest
    Assert-FailedWith $ReleaseReadyResult "distribution gate\(s\) are not approved" "Current ReleaseReady gate"

    Write-Output "ARTIFACT_CONTRACT_NEGATIVE_TESTS=PASS"
    Write-Output "CASES=11"
    Write-Output "NETWORK_ACTIONS=0"
}
finally {
    foreach ($FixturePath in $FixturePaths) {
        if (Test-Path -LiteralPath $FixturePath) {
            Remove-Item -LiteralPath $FixturePath -Force
        }
    }
}
