@echo off
:: ml/seed-models.bat — Download model weights vào local cache (Windows)
::
:: Usage:
::   scripts\ml\seed-models.bat
::   scripts\ml\seed-models.bat --model mobilenet
::   scripts\ml\seed-models.bat --list
::
:: Yêu cầu:
::   docker compose up -d mlflow  (tuỳ chọn — tạo placeholder nếu không có)
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\.."
set "MODEL_DIR=%PROJECT_ROOT%\backend\data\models"

set "MODEL_FILTER="
set "LIST_ONLY=false"

:parse
if "%~1"=="" goto done_parse
if /i "%~1"=="--model" (set "MODEL_FILTER=%~2" & shift & shift & goto parse)
if /i "%~1"=="--list"  (set "LIST_ONLY=true"   & shift          & goto parse)
if /i "%~1"=="--help"  goto show_help
if /i "%~1"=="-h"      goto show_help
shift & goto parse

:show_help
echo Usage: %~nx0 [--model ^<name^>] [--list]
echo   --model ^<name^>   Download chỉ model này
echo   --list            Liệt kê model khả dụng
endlocal & exit /b 0

:done_parse

echo.
echo === VietCropDoctor — Seed Models ===
echo.

if "!LIST_ONLY!"=="true" (
    echo Models khả dụng:
    echo   efficientnet_b0
    echo   mobilenetv3_large
    echo   resnet50
    echo   vit_base
    echo   yolov11
    echo.
    endlocal & exit /b 0
)

if not exist "%MODEL_DIR%" mkdir "%MODEL_DIR%"

curl -sf http://localhost:5000/health >nul 2>&1
if not errorlevel 1 (
    echo [OK]   MLflow reachable at http://localhost:5000
    set "USE_MLFLOW=true"
) else (
    echo [WARN] MLflow không chạy — sẽ tạo placeholder weights
    set "USE_MLFLOW=false"
)
echo.

set "MODELS=efficientnet_b0 mobilenetv3_large resnet50 vit_base yolov11"
if defined MODEL_FILTER set "MODELS=%MODEL_FILTER%"

for %%M in (!MODELS!) do (
    if not exist "%MODEL_DIR%\%%M" mkdir "%MODEL_DIR%\%%M"

    if "!USE_MLFLOW!"=="true" (
        echo [INFO] Fetching %%M từ MLflow...
        docker exec vcd-mlflow python -c ^
            "import mlflow; mlflow.set_tracking_uri('http://localhost:5000'); c=mlflow.MlflowClient(); exp=c.get_experiment_by_name('vietcropdoctor-classification'); runs=c.search_runs(exp.experiment_id,filter_string=\"tags.model_name='%%M'\",order_by=['start_time DESC'],max_results=1) if exp else []; mlflow.artifacts.download_artifacts(run_id=runs[0].info.run_id,artifact_path='model',dst_path='%MODEL_DIR%/%%M') if runs else print('No runs for %%M')" ^
            2>nul || echo [WARN] MLflow fetch không thành công cho %%M
    ) else (
        echo placeholder - replace with actual weights > "%MODEL_DIR%\%%M\README.txt"
    )
    echo [OK]   %%M -^> %MODEL_DIR%\%%M
)

echo.
echo [OK]   Model seeding xong.
echo        Model directory: %MODEL_DIR%
echo        Cập nhật MODEL_PATH trong .env để trỏ đến checkpoint mong muốn.
endlocal
