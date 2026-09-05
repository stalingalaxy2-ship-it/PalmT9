@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo   掌上九键 PalmT9 一键启动
echo ==========================================
python launcher.py
if errorlevel 1 (
    echo.
    echo 运行出错, 详情见 palm_t9.log
    pause
)
