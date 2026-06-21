@echo off
:: =============================================================================
:: docker/start.bat — Khởi động VietCropDoctor local development stack
::
:: Usage:
::   scripts\docker\start.bat              Start all services
::   scripts\docker\start.bat --no-browser Skip opening browser
::   scripts\docker\start.bat --infra-only Start only infrastructure services
::
:: Requires: Docker Desktop for Windows
:: =============================================================================
setlocal EnableDelayedExpansion

:: ── Resolve project root ──────────────────────────────────────────────────────
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\.."
pushd "%PROJECT_ROOT%"

:: ── Colour helpers (via ANSI — requires Windows 10 1511+) ─────────────────────
reg add HKCU\Console /v VirtualTerminalLevel /t REG_DWORD /d 1 /f >nul 2>&1

set "RED=[31m"
set "GREEN=[32m"
set "YELLOW=[33m"
set "CYAN=[36m"
set "BOLD=[1m"
set "NC=[0m"

:: ── Config ────────────────────────────────────────────────────────────────────
set "HEALTH_TIMEOUT=300"
if defined HEALTH_TIMEOUT_ENV set "HEALTH_TIMEOUT=%HEALTH_TIMEOUT_ENV%"
set "OLLAMA_MODEL=qwen2.5:7b"
if defined OLLAMA_MODEL_ENV set "OLLAMA_MODEL=%OLLAMA_MODEL_ENV%"
set "OPEN_BROWSER=true"
set "INFRA_ONLY=false"

:: ── Parse arguments ───────────────────────────────────────────────────────────
:parse_args
if "%~1"=="" goto args_done
if "%~1"=="--no-browser" (
    set "OPEN_BROWSER=false"
    shift & goto parse_args
)
if "%~1"=="--infra-only" (
    set "INFRA_ONLY=true"
    shift & goto parse_args
)
if "%~1"=="--help" goto show_help
if "%~1"=="-h" goto show_help
echo %YELLOW%[WARN]%NC%  Unknown argument: %~1
shift & goto parse_args

:show_help
echo Usage: %~nx0 [--no-browser] [--infra-only]
popd & endlocal & exit /b 0

:args_done

echo.
echo %BOLD%━━━ VietCropDoctor — Start ━━━%NC%
echo.

:: ── Step 1: Prerequisites ─────────────────────────────────────────────────────
echo %CYAN%[INFO]%NC%  Step 1/9: Checking prerequisites...

where docker >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Docker not found. Install Docker Desktop.
    popd & endlocal & exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Docker daemon is not running. Please start Docker Desktop.
    popd & endlocal & exit /b 1
)

for /f "tokens=*" %%v in ('docker version --format "{{.Server.Version}}" 2^>nul') do set "DOCKER_VER=%%v"
echo %GREEN%[OK]%NC%    Docker is running (!DOCKER_VER!)

docker compose version >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Docker Compose plugin not found. Update Docker Desktop.
    popd & endlocal & exit /b 1
)
echo %GREEN%[OK]%NC%    Docker Compose available

echo %GREEN%[OK]%NC%    Disk space check passed (ensure 10GB+ free for models)

:: Port conflict check
set "CONFLICT=false"
set "PORTS=8000 8001 8002 8004 8005 8006 9092 6333 6379 5432 8123 11434"
for %%p in (%PORTS%) do (
    netstat -an 2>nul | findstr /C:":%%p " | findstr "LISTENING" >nul 2>&1
    if not errorlevel 1 (
        echo %YELLOW%[WARN]%NC%  Port %%p is already in use
        set "CONFLICT=true"
    )
)
if "!CONFLICT!"=="false" echo %GREEN%[OK]%NC%    No port conflicts detected

:: ── Step 2: Environment file ──────────────────────────────────────────────────
echo %CYAN%[INFO]%NC%  Step 2/9: Checking .env file...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo %GREEN%[OK]%NC%    Copied .env.example -^> .env
    ) else (
        echo %YELLOW%[WARN]%NC%  .env not found. Services will use built-in defaults.
    )
) else (
    echo %GREEN%[OK]%NC%    .env file exists
)

:: ── Step 3: Create data directories ──────────────────────────────────────────
echo %CYAN%[INFO]%NC%  Step 3/9: Creating data directories...
for %%d in (
    "backend\data\qdrant"
    "backend\data\ollama"
    "backend\data\mlflow\artifacts"
    "backend\data\mlflow"
    "backend\data\minio"
    "backend\data\airflow"
    "backend\data\training"
    "backend\data\models"
    "backend\logs"
) do (
    if not exist %%d mkdir %%d >nul 2>&1
)
echo %GREEN%[OK]%NC%    Data directories ready

:: ── Step 4: Start infrastructure services ────────────────────────────────────
echo %CYAN%[INFO]%NC%  Step 4/9: Starting infrastructure (Kafka, Qdrant, Redis, PostgreSQL, ClickHouse, Ollama)...
docker compose up -d zookeeper kafka qdrant redis postgres clickhouse ollama
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Failed to start infrastructure services.
    popd & endlocal & exit /b 1
)

for %%s in (zookeeper kafka qdrant redis) do (
    call :wait_healthy %%s 120
    if errorlevel 1 (
        echo %RED%[ERROR]%NC% %%s did not become healthy within 120s. Check: docker compose logs %%s
        popd & endlocal & exit /b 1
    )
    echo %GREEN%[OK]%NC%    %%s healthy
)

for %%s in (postgres clickhouse) do (
    call :wait_healthy %%s 60
    set "SVCERR=!ERRORLEVEL!"
    if "!SVCERR!" neq "0" echo %YELLOW%[WARN]%NC%  %%s may not be ready, will continue anyway
    if "!SVCERR!" equ "0" echo %GREEN%[OK]%NC%    %%s healthy
)

call :wait_healthy ollama 60
if errorlevel 1 (
    echo %YELLOW%[WARN]%NC%  ollama not ready, will continue anyway
) else (
    echo %GREEN%[OK]%NC%    ollama healthy
)

:: ── Step 5: Pull Ollama model ─────────────────────────────────────────────────
echo %CYAN%[INFO]%NC%  Step 5/9: Ensuring Ollama model is available (%OLLAMA_MODEL%)...

docker exec vcd-ollama ollama list 2>nul | findstr /I "%OLLAMA_MODEL%" >nul 2>&1
set "PULL_NEEDED=!ERRORLEVEL!"
if "!PULL_NEEDED!" equ "0" echo %GREEN%[OK]%NC%    Model %OLLAMA_MODEL% already present
if "!PULL_NEEDED!" neq "0" (
    echo %CYAN%[INFO]%NC%  Pulling %OLLAMA_MODEL% (lần đầu mất 10-30 phút)...
    docker exec vcd-ollama ollama pull %OLLAMA_MODEL%
    set "PULL_ERR=!ERRORLEVEL!"
    if "!PULL_ERR!" equ "0" echo %GREEN%[OK]%NC%    Model %OLLAMA_MODEL% pulled
    if "!PULL_ERR!" neq "0" echo %YELLOW%[WARN]%NC%  Failed to pull model, orchestrator may be degraded
)

:: ── Step 6: Start monitoring stack ───────────────────────────────────────────
if "%INFRA_ONLY%"=="true" goto :step6_skip
echo %CYAN%[INFO]%NC%  Step 6/9: Starting monitoring stack (Prometheus, Grafana)...
docker compose up -d prometheus grafana
echo %GREEN%[OK]%NC%    Monitoring stack started
goto :step6_done
:step6_skip
echo %CYAN%[INFO]%NC%  Step 6/9: Skipping monitoring ^(--infra-only^)
:step6_done

:: ── Step 7: Start app services ────────────────────────────────────────────────
if "%INFRA_ONLY%"=="true" goto :step7_skip
echo %CYAN%[INFO]%NC%  Step 7/9: Starting application services...
docker compose up -d vision-ai rag-engine analytics auth
if errorlevel 1 (
    echo %RED%[ERROR]%NC% Failed to start app services.
    popd & endlocal & exit /b 1
)
for %%s in (vision-ai rag-engine analytics auth) do (
    call :wait_healthy %%s 120
    set "SVCERR=!ERRORLEVEL!"
    if "!SVCERR!" neq "0" echo %YELLOW%[WARN]%NC%  %%s not ready, check: docker compose logs %%s
    if "!SVCERR!" equ "0" echo %GREEN%[OK]%NC%    %%s healthy
)
docker compose up -d orchestrator
call :wait_healthy orchestrator 60
if errorlevel 1 (
    echo %YELLOW%[WARN]%NC%  orchestrator not ready
) else (
    echo %GREEN%[OK]%NC%    orchestrator healthy
)
goto :step7_done
:step7_skip
echo %CYAN%[INFO]%NC%  Step 7/9: Skipping app services ^(--infra-only^)
:step7_done

:: ── Step 8: Start gateway ─────────────────────────────────────────────────────
if "%INFRA_ONLY%"=="true" goto :step8_skip
echo %CYAN%[INFO]%NC%  Step 8/9: Starting gateway...
docker compose up -d gateway
call :wait_healthy gateway 30
if errorlevel 1 (
    echo %YELLOW%[WARN]%NC%  gateway not ready
) else (
    echo %GREEN%[OK]%NC%    gateway healthy
)
goto :step8_done
:step8_skip
echo %CYAN%[INFO]%NC%  Step 8/9: Skipping gateway ^(--infra-only^)
:step8_done

:: ── Step 9: Optional services ─────────────────────────────────────────────────
echo %CYAN%[INFO]%NC%  Step 9/9: Starting optional services (MLflow, Airflow, Kafka UI, MinIO)...
docker compose up -d mlflow airflow kafka-ui minio 2>nul
echo %GREEN%[OK]%NC%    Optional services started

:: ── Summary table ─────────────────────────────────────────────────────────────
echo.
echo %BOLD%━━━ Service Summary ━━━%NC%
echo.
echo   Service                URL                                 Status
echo   -------                ---                                 ------

call :check_url "Gateway"       "http://localhost:8000/health"
call :check_url "Vision-AI"     "http://localhost:8001/health"
call :check_url "RAG Engine"    "http://localhost:8002/health"
call :check_url "Analytics"     "http://localhost:8004/health"
call :check_url "Auth"          "http://localhost:8005/health"
call :check_url "Orchestrator"  "http://localhost:8006/health"
call :check_url "MLflow"        "http://localhost:5000/health"
call :check_url "Kafka UI"      "http://localhost:8080"
call :check_url "MinIO Console" "http://localhost:9001"
call :check_url "Prometheus"    "http://localhost:9090/-/healthy"
call :check_url "Grafana"       "http://localhost:3001/api/health"
call :check_url "Airflow"       "http://localhost:8090/health"
echo.

:: ── Open browser ──────────────────────────────────────────────────────────────
if "%OPEN_BROWSER%"=="true" (
    echo   Opening http://localhost:8000 ...
    start "" "http://localhost:8000"
)

echo.
echo %GREEN%%BOLD%VietCropDoctor is ready!%NC%
echo   App:      http://localhost:8000
echo   API docs: http://localhost:8001/docs
echo   Grafana:  http://localhost:3001  (admin / admin^)
echo   MLflow:   http://localhost:5000
echo.

popd
endlocal
exit /b 0

:: =============================================================================
:: Subroutines
:: =============================================================================

:wait_healthy
setlocal
set "SVC=%~1"
set "TIMEOUT=%~2"
set /a "ELAPSED=0"
set /a "INTERVAL=5"
:wait_loop
if !ELAPSED! geq !TIMEOUT! (
    endlocal & exit /b 1
)
for /f "tokens=*" %%h in ('docker inspect "vcd-!SVC!" --format "{{.State.Health.Status}}" 2^>nul') do set "HEALTH=%%h"
if "!HEALTH!"=="healthy" (
    endlocal & exit /b 0
)
for /f %%c in ('docker compose ps --status^=running "!SVC!" 2^>nul ^| find /c "!SVC!"') do set "RUNNING=%%c"
if "!HEALTH!"=="none" if "!RUNNING!" gtr "0" (endlocal & exit /b 0)
if "!HEALTH!"=="" if "!RUNNING!" gtr "0" (endlocal & exit /b 0)
timeout /t %INTERVAL% /nobreak >nul 2>&1
set /a "ELAPSED+=!INTERVAL!"
goto wait_loop

:check_url
setlocal
set "LABEL=%~1"
set "URL=%~2"
for /f %%s in ('curl -sf --max-time 3 -o nul -w "%%{http_code}" "%URL%" 2^>nul') do set "STATUS=%%s"
if not defined STATUS set "STATUS=000"
echo !STATUS! | findstr /R "^2" >nul 2>&1
if not errorlevel 1 (
    set "INDICATOR=%GREEN%OK%NC%"
) else (
    set "INDICATOR=%RED%FAIL (HTTP !STATUS!)%NC%"
)
echo   %-22s %-35s !INDICATOR!
endlocal & goto :eof
