@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title AI+舆情检测系统 传统GUI
echo ============================================
echo        AI+舆情检测系统 传统GUI
echo ============================================
echo.
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo 未找到 Python，请确认 Python 已安装并已加入 PATH
    pause
    exit /b 1
)
python -B "%~dp0gui.py"
set "app_exit_code=%errorlevel%"
if not "%app_exit_code%"=="0" (
    echo.
    echo 程序异常退出，请检查上方错误信息
    pause
)
endlocal & exit /b %app_exit_code%
