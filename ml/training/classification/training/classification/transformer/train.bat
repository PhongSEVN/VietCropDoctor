@echo off
REM Train Vision Transformer (ViT). Calls the datn_python venv interpreter directly
REM (no activation needed). cd /d %~dp0 makes "train.py" resolve from anywhere.
cd /d "%~dp0"
"C:\Users\THIS PC\Desktop\envs\datn_python\Scripts\python.exe" train.py
pause
