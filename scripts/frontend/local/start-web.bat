@echo off
:: frontend/local/start-web.bat — Khởi động React dev server trên Windows
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\..\.."
set "WEB_DIR=%PROJECT_ROOT%client\web"

pushd "%WEB_DIR%"
if errorlevel 1 (
    echo [ERROR] Không tìm thấy thư mục client\web
    endlocal & exit /b 1
)

if not exist "node_modules" (
    echo [INFO] node_modules chưa có — chạy npm install...
    npm install
    if errorlevel 1 (
        echo [ERROR] npm install thất bại.
        popd & endlocal & exit /b 1
    )
)

echo [INFO] Khởi động React dev server...
echo [INFO] URL: http://localhost:5173
echo.
npm run dev

popd
endlocal