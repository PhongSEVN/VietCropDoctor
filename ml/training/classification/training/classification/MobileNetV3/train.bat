@echo off
REM Train MobileNetV3-Large. Calls the datn_python venv interpreter directly (no
REM activation needed). cd /d %~dp0 makes "train.py" resolve from anywhere.
cd /d "%~dp0"
"C:\Users\THIS PC\Desktop\envs\datn_python\Scripts\python.exe" train.py
pause
