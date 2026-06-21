@echo off
:: test/gateway/run.bat — Chạy gateway integration tests trên Windows
::
:: Usage:
::   scripts\test\gateway\run.bat                   Tất cả tests
::   scripts\test\gateway\run.bat test_rbac.py      Chỉ RBAC
::   scripts\test\gateway\run.bat -k test_login     Filter theo tên
::   set GATEWAY_URL=http://staging:8000 && scripts\test\gateway\run.bat
::
:: Yêu cầu:
::   docker compose up -d postgres redis auth gateway
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "TEST_DIR=%SCRIPT_DIR%..\..\..\test system\gateway"

if not defined GATEWAY_URL set "GATEWAY_URL=http://localhost:8000"

echo === VietCropDoctor — Gateway Tests ===
echo   Gateway : %GATEWAY_URL%
echo   Dir     : %TEST_DIR%
echo.

pushd "%TEST_DIR%"
if errorlevel 1 (
    echo [ERROR] Không tìm thấy thư mục: %TEST_DIR%
    endlocal & exit /b 1
)

where pytest >nul 2>&1
if errorlevel 1 (
    echo [INFO] Cài test dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] pip install thất bại.
        popd & endlocal & exit /b 1
    )
)

set "GATEWAY_URL=%GATEWAY_URL%"
pytest -v %*

popd
endlocal
