$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BasePython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$RuntimePython = Join-Path $ProjectRoot ".scrapling-venv\Scripts\python.exe"
$BrowserRoot = Join-Path $ProjectRoot ".scrapling-runtime\playwright"
$Requirements = Join-Path $ProjectRoot "requirements-scrapling.txt"

if (-not (Test-Path -LiteralPath $BasePython -PathType Leaf)) {
    throw "主项目 Python 不存在：$BasePython"
}

if (-not (Test-Path -LiteralPath $RuntimePython -PathType Leaf)) {
    & $BasePython -m venv (Join-Path $ProjectRoot ".scrapling-venv")
}

& $RuntimePython -m pip install --upgrade pip
& $RuntimePython -m pip install -r $Requirements

$env:PLAYWRIGHT_BROWSERS_PATH = $BrowserRoot
& (Join-Path $ProjectRoot ".scrapling-venv\Scripts\scrapling.exe") install

& $RuntimePython -c "import scrapling; print('Scrapling runtime ready:', scrapling.__version__)"
