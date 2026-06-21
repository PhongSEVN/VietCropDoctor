@echo off
:: start/local/start.bat — Khởi động toàn bộ môi trường local dev (Windows)
::
:: Wrapper gọi docker/start.bat rồi mở React dev server trong cửa sổ mới.
::
:: Usage:
::   scripts\start\local\start.bat
::   scripts\start\local\start.bat --infra-only   Chỉ Docker, không mở React
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "DOCKER_START=%SCRIPT_DIR%..\..\docker\start.bat"
set "WEB_START=%SCRIPT_DIR%..\..\frontend\local\start-web.bat"

set "INFRA_ONLY=false"
for %%A in (%*) do (
    if "%%A"=="--infra-only" set "INFRA_ONLY=true"
)

echo === VietCropDoctor — Local Dev Start ===
echo.

call "%DOCKER_START%" %*
if errorlevel 1 (
    echo [ERROR] Docker stack khởi động thất bại.
    endlocal & exit /b 1
)

if "!INFRA_ONLY!"=="true" (
    echo [INFO] --infra-only: bỏ qua React dev server.
    endlocal & exit /b 0
)

echo.
echo [INFO] Mở React dev server trong cửa sổ mới...
start "React Dev Server" cmd /k "call "%WEB_START%""

echo.
echo [OK]   Stack đã chạy.
echo        App:     http://localhost:8000
echo        React:   http://localhost:5173  (dev — nếu bỏ qua gateway)
endlocal
