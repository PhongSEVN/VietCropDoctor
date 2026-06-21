@echo off
:: test/local/run-all.bat — Chạy toàn bộ integration test suite (Windows)
::
:: Usage:
::   scripts\test\local\run-all.bat
::   scripts\test\local\run-all.bat -k test_login    Filter theo tên
::
:: Yêu cầu:
::   docker compose up -d postgres redis auth gateway
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "GATEWAY_DIR=%SCRIPT_DIR%..\gateway"

if not defined GATEWAY_URL set "GATEWAY_URL=http://localhost:8000"

echo === VietCropDoctor — Full Test Suite ===
echo   Gateway : %GATEWAY_URL%
echo.

call "%GATEWAY_DIR%\run.bat" %*

endlocal
