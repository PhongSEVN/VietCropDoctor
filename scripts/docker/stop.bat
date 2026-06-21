@echo off
:: =============================================================================
:: docker/stop.bat — Dừng VietCropDoctor local development stack
::
:: Usage:
::   scripts\docker\stop.bat           Graceful stop (keep volumes)
::   scripts\docker\stop.bat --clean   Stop + remove volumes + prune images
::
:: Requires: Docker Desktop for Windows
:: =============================================================================
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\.."
pushd "%PROJECT_ROOT%"

reg add HKCU\Console /v VirtualTerminalLevel /t REG_DWORD /d 1 /f >nul 2>&1

set "RED=[31m"
set "GREEN=[32m"
set "YELLOW=[33m"
set "CYAN=[36m"
set "BOLD=[1m"
set "NC=[0m"

set "CLEAN=false"

:parse_args
if "%~1"=="" goto args_done
if "%~1"=="--clean" (
    set "CLEAN=true"
    shift & goto parse_args
)
if "%~1"=="--help" goto show_help
if "%~1"=="-h" goto show_help
echo %YELLOW%[WARN]%NC%  Unknown argument: %~1
shift & goto parse_args

:show_help
echo Usage: %~nx0 [--clean]
echo   --clean   Also remove volumes and prune dangling images
popd & endlocal & exit /b 0

:args_done

echo.
echo %BOLD%━━━ VietCropDoctor — Stop ━━━%NC%
echo.

echo %CYAN%[INFO]%NC%  Stopping all services...

if "!CLEAN!"=="true" (
    docker compose down -v --remove-orphans
    if errorlevel 1 (
        echo %RED%[ERROR]%NC% Failed to stop services.
        popd & endlocal & exit /b 1
    )
    echo %GREEN%[OK]%NC%    Services stopped and volumes removed

    echo %CYAN%[INFO]%NC%  Pruning dangling images...
    docker image prune -f >nul 2>&1
    echo %GREEN%[OK]%NC%    Dangling images pruned
) else (
    docker compose down --remove-orphans
    if errorlevel 1 (
        echo %RED%[ERROR]%NC% Failed to stop services.
        popd & endlocal & exit /b 1
    )
    echo %GREEN%[OK]%NC%    Services stopped (data volumes preserved^)
    echo %CYAN%[INFO]%NC%  Run with --clean to also remove volumes and prune images
)

echo.
echo %CYAN%[INFO]%NC%  Docker disk usage after stop:
docker system df
echo.
echo %GREEN%[OK]%NC%    VietCropDoctor stack stopped.
echo.

popd
endlocal
exit /b 0
