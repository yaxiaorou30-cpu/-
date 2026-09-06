@echo off
setlocal
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0.runtime\launcher\Start-AIOpinionMonitor.ps1" %*
set "launcher_exit=%ERRORLEVEL%"
if not "%launcher_exit%"=="0" (
    echo.
    echo Startup failed. Keep this window open and see the user guide.
    if "%~1"=="" pause
)
endlocal & exit /b %launcher_exit%
