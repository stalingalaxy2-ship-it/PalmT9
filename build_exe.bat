@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo   PalmT9 打包成独立 exe (PyInstaller)
echo ==========================================
echo.
python -m pip install pyinstaller 2>nul
python -m PyInstaller --onefile --name PalmT9 ^
    --add-data "hand_landmarker.task;." ^
    --collect-all mediapipe ^
    --collect-all cv2 ^
    --collect-all PIL ^
    palm_t9.py
echo.
echo 打包结果在 dist\PalmT9.exe
pause
