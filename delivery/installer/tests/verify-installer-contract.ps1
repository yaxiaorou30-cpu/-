[CmdletBinding()]
param(
    [string]$ContractPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($ContractPath)) {
    $ContractPath = Join-Path $PSScriptRoot "..\installer-contract.json"
}

function Assert-Equal {
    param(
        [Parameter(Mandatory = $true)]$Actual,
        [Parameter(Mandatory = $true)]$Expected,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if ($Actual -ne $Expected) {
        throw "$Label must be '$Expected'; got '$Actual'."
    }
}

function Assert-False {
    param(
        [Parameter(Mandatory = $true)]$Actual,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if ($Actual -ne $false) {
        throw "$Label must be false."
    }
}

function Assert-Sequence {
    param(
        [Parameter(Mandatory = $true)][object[]]$Actual,
        [Parameter(Mandatory = $true)][object[]]$Expected,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $ActualText = (@($Actual) | ConvertTo-Json -Compress)
    $ExpectedText = (@($Expected) | ConvertTo-Json -Compress)
    if ($ActualText -ne $ExpectedText) {
        throw "$Label differs. Expected $ExpectedText; got $ActualText."
    }
}

function Assert-Contains {
    param(
        [Parameter(Mandatory = $true)][object[]]$Actual,
        [Parameter(Mandatory = $true)]$Expected,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if ($Expected -notin @($Actual)) {
        throw "$Label must contain '$Expected'."
    }
}

if (-not (Test-Path -LiteralPath $ContractPath -PathType Leaf)) {
    throw "Missing installer contract: $ContractPath"
}

$Contract = Get-Content -Raw -Encoding UTF8 -LiteralPath $ContractPath | ConvertFrom-Json

Assert-Equal $Contract.schemaVersion 1 "schemaVersion"
Assert-Equal $Contract.product.appId "E30332CB-8174-4589-978B-7ED8546CBD60" "product.appId"
Assert-Equal $Contract.product.baselineCommit "b7a95a783088dd1b7ca5b79dc33302fa102479c9" "product.baselineCommit"
Assert-Equal $Contract.product.platform "windows-11-x64" "product.platform"

Assert-Equal $Contract.install.scope "current-user" "install.scope"
Assert-Equal $Contract.install.root "%LOCALAPPDATA%\Programs\AI-Opinion-Monitor" "install.root"
Assert-Equal $Contract.install.deliveryMode "online" "install.deliveryMode"
Assert-Equal $Contract.install.copyPolicy "allowlist-only" "install.copyPolicy"
Assert-False $Contract.install.requiresAdministrator "install.requiresAdministrator"
Assert-False $Contract.install.modifiesPath "install.modifiesPath"
Assert-False $Contract.install.registersPython "install.registersPython"

Assert-Equal $Contract.runtime.python.implementation "cpython" "runtime.python.implementation"
Assert-Equal $Contract.runtime.python.version "3.13.9" "runtime.python.version"
Assert-Equal $Contract.runtime.python.architecture "x64" "runtime.python.architecture"
Assert-Equal $Contract.runtime.python.installDirectory ".runtime\python" "runtime.python.installDirectory"
Assert-False $Contract.runtime.python.useSystemPython "runtime.python.useSystemPython"
Assert-Equal $Contract.runtime.uv.version "0.10.8" "runtime.uv.version"
Assert-Equal $Contract.runtime.uv.executableSha256 "067CF5D81A2DC006C1C76FA160B4DA96A35BC80900C22FAED7ACFC52510FCDF5" "runtime.uv.executableSha256"
Assert-Sequence @($Contract.runtime.privateEnvironmentPaths) @(
    ".venv",
    ".scrapling-venv",
    "opensource_candidates\bilibili-cli\.venv",
    "opensource_candidates\newspaper4k\.venv",
    "opensource_candidates\aiotieba\.venv"
) "runtime.privateEnvironmentPaths"

Assert-Equal $Contract.launch.interpreter ".venv\Scripts\python.exe" "launch.interpreter"
Assert-Equal $Contract.launch.entrypoint "web_app.py" "launch.entrypoint"
Assert-Equal $Contract.launch.host "127.0.0.1" "launch.host"
Assert-Equal $Contract.launch.basePort 8765 "launch.basePort"
Assert-Equal $Contract.launch.portSearchCount 20 "launch.portSearchCount"
Assert-Equal $Contract.launch.healthPath "/api/auth/status" "launch.healthPath"
Assert-Equal $Contract.launch.processWindowStyle "hidden" "launch.processWindowStyle"
Assert-Equal $Contract.launch.stopMode "verified-pid-termination" "launch.stopMode"
Assert-False $Contract.launch.allowSystemPythonFallback "launch.allowSystemPythonFallback"
Assert-False $Contract.launch.claimsGracefulExternalStop "launch.claimsGracefulExternalStop"
Assert-Sequence @($Contract.launch.arguments) @(
    "--host",
    "127.0.0.1",
    "--port",
    "8765",
    "--no-browser"
) "launch.arguments"

Assert-Sequence @($Contract.userData.installRelativePaths) @("data", "output") "userData.installRelativePaths"
Assert-Sequence @($Contract.userData.externalPaths) @("%LOCALAPPDATA%\AI-Opinion-Monitor\sensitive") "userData.externalPaths"
Assert-False $Contract.userData.overwriteDuringRepair "userData.overwriteDuringRepair"
Assert-False $Contract.userData.overwriteDuringUpgrade "userData.overwriteDuringUpgrade"
Assert-False $Contract.userData.removeDuringUninstall "userData.removeDuringUninstall"
Assert-False $Contract.userData.offerRemovalOption "userData.offerRemovalOption"

Assert-False $Contract.credentials.installerCollectsValues "credentials.installerCollectsValues"
Assert-False $Contract.credentials.packageContainsValues "credentials.packageContainsValues"
Assert-Sequence @($Contract.credentials.environmentVariableNames) @(
    "BAIDU_QIANFAN_API_KEY",
    "DEEPSEEK_API_KEY"
) "credentials.environmentVariableNames"

Assert-Equal $Contract.browser.installDirectory ".runtime\browsers" "browser.installDirectory"
Assert-False $Contract.browser.useSharedSystemCache "browser.useSharedSystemCache"

Assert-Equal $Contract.adapterDeliveryMatrix.scrapling "prototype-target" "adapterDeliveryMatrix.scrapling"
Assert-Equal $Contract.adapterDeliveryMatrix.'bilibili-cli' "prototype-only-pending-d4-license" "adapterDeliveryMatrix.bilibili-cli"
Assert-Equal $Contract.adapterDeliveryMatrix.newspaper4k "prototype-target" "adapterDeliveryMatrix.newspaper4k"
Assert-Equal $Contract.adapterDeliveryMatrix.aiotieba "prototype-target" "adapterDeliveryMatrix.aiotieba"
Assert-Equal $Contract.adapterDeliveryMatrix.'xhs-cli' "not-delivered-source-policy-disabled" "adapterDeliveryMatrix.xhs-cli"
Assert-Equal $Contract.adapterDeliveryMatrix.crawl4weibo "not-delivered-source-policy-disabled" "adapterDeliveryMatrix.crawl4weibo"

Assert-Contains @($Contract.workspaceSourceExclusions) ".codex_tmp/" "workspaceSourceExclusions"
Assert-Contains @($Contract.workspaceSourceExclusions) "requirements/" "workspaceSourceExclusions"
Assert-Contains @($Contract.workspaceSourceExclusions) "data/" "workspaceSourceExclusions"
$LegacyLauncherName = ([string][char]0x542F) + ([char]0x52A8) + ".bat"
Assert-Contains @($Contract.workspaceSourceExclusions) $LegacyLauncherName "workspaceSourceExclusions"
if ("requirements.txt" -in @($Contract.workspaceSourceExclusions)) {
    throw "workspaceSourceExclusions must distinguish requirements/ from requirements.txt."
}

Write-Output "INSTALLER_CONTRACT=PASS"
