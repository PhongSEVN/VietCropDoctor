@echo off
REM ===========================================================================
REM Train 4 torch models sequentially (overnight). Transformer/ViT runs LAST.
REM Each model logs to train4_<name>.log next to this file. If one model fails
REM (e.g. OOM) the batch continues with the next one, so one crash does not
REM waste the whole night. Metrics also go to MLflow (:5000).
REM ===========================================================================
setlocal
set "PY=C:\Users\THIS PC\Desktop\envs\datn_python\Scripts\python.exe"
set "BASE=%~dp0"
REM Force UTF-8 stdout so MLflow's emoji output doesn't crash on the cp1252 console.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

REM Make sure MLflow is up (no-op if already running). Wait a bit for the server.
docker start vcd-mlflow
timeout /t 15 /nobreak >nul

echo ===========================================================================
echo [1/4] EfficientB0   start: %DATE% %TIME%
echo ===========================================================================
cd /d "%BASE%EfficientB0"
"%PY%" train.py > "%BASE%train4_efficientb0.log" 2>&1
echo     EfficientB0 done: %DATE% %TIME%

echo ===========================================================================
echo [2/4] MobileNetV3   start: %DATE% %TIME%
echo ===========================================================================
cd /d "%BASE%MobileNetV3"
"%PY%" train.py > "%BASE%train4_mobilenetv3.log" 2>&1
echo     MobileNetV3 done: %DATE% %TIME%

echo ===========================================================================
echo [3/4] ResNet50      start: %DATE% %TIME%
echo ===========================================================================
cd /d "%BASE%Resnet50"
"%PY%" train.py > "%BASE%train4_resnet50.log" 2>&1
echo     ResNet50 done: %DATE% %TIME%

echo ===========================================================================
echo [4/4] Transformer / ViT  (LAST)   start: %DATE% %TIME%
echo ===========================================================================
cd /d "%BASE%transformer"
"%PY%" train.py > "%BASE%train4_transformer.log" 2>&1
echo     Transformer done: %DATE% %TIME%

echo ===========================================================================
echo ALL 4 MODELS FINISHED  %DATE% %TIME%
echo Logs: train4_*.log    Metrics: MLflow http://localhost:5000
echo ===========================================================================
pause
