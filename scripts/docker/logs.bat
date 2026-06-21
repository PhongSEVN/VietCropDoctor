@echo off
:: =============================================================================
:: docker/logs.bat — Xem logs cho VietCropDoctor services
::
:: Usage:
::   scripts\docker\logs.bat                        Aggregate logs from all app services
::   scripts\docker\logs.bat vision-ai              Logs for a specific service
::   scripts\docker\logs.bat vision-ai --no-follow  Print and exit
::   scripts\docker\logs.bat --tail=100             Show last N lines (default 50)
::
:: Requires: Docker Desktop for Windows
:: =============================================================================
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\.."
pushd "%PROJECT_ROOT%"

reg add HKCU\Console /v VirtualTerminalLevel /t REG_DWORD /d 1 /f >nul 2>&1

set "YELLOW=[33m"
set "CYAN=[36m"
set "BOLD=[1m"
set "NC=[0m"

set "FOLLOW=true"
set "TAIL=50"
set "SERVICE="

:parse_args
if "%~1"=="" goto args_done
if "%~1"=="--no-follow" (
    set "FOLLOW=false"
    shift & goto parse_args
)
if "%~1"=="--help" goto show_help
if "%~1"=="-h" goto show_help

echo %~1 | findstr /R "^--tail=" >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=2 delims==" %%v in ("%~1") do set "TAIL=%%v"
    shift & goto parse_args
)

echo %~1 | findstr /R "^-" >nul 2>&1
if errorlevel 1 (
    if "!SERVICE!"=="" (
        set "SERVICE=%~1"
    )
)
shift & goto parse_args

:show_help
echo Usage: %~nx0 [service-name] [--no-follow] [--tail=N]
echo.
echo   service-name   vision-ai, rag-engine, analytics, auth,
echo                  orchestrator, gateway, kafka, qdrant, redis, ...
echo   --no-follow    Print logs and exit
echo   --tail=N       Show last N lines (default: 50^)
popd & endlocal & exit /b 0

:args_done

set "APP_SERVICES=vision-ai rag-engine analytics auth orchestrator gateway"

set "FOLLOW_FLAG=-f"
if "!FOLLOW!"=="false" set "FOLLOW_FLAG="

if not "!SERVICE!"=="" (
    echo %CYAN%[INFO]%NC%  Showing logs for: %BOLD%!SERVICE!%NC%
    if "!FOLLOW!"=="true" echo %CYAN%[INFO]%NC%  Press Ctrl+C to stop
    echo.
    docker compose logs !FOLLOW_FLAG! --tail=!TAIL! !SERVICE!
) else (
    echo %CYAN%[INFO]%NC%  Showing aggregated logs from all app services
    if "!FOLLOW!"=="true" echo %CYAN%[INFO]%NC%  Press Ctrl+C to stop
    echo %CYAN%[INFO]%NC%  Services: !APP_SERVICES!
    echo.
    docker compose logs !FOLLOW_FLAG! --tail=!TAIL! !APP_SERVICES!
)

popd
endlocal
exit /b 0
