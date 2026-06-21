@echo off
REM Train YOLOv8-cls. Calls the datn_python venv interpreter directly (no activation
REM needed). cd /d %~dp0 makes "train_yolo.py" resolve no matter where it's launched.
cd /d "%~dp0"
"C:\Users\THIS PC\Desktop\envs\datn_python\Scripts\python.exe" train_yolo.py
pause
