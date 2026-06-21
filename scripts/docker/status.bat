@echo off
:: =============================================================================
:: docker/status.bat — Hiển thị trạng thái VietCropDoctor stack
::
:: Usage:
::   scripts\docker\status.bat          Full status report
::   scripts\docker\status.bat --short  Container list only
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

set "SHORT=false"

:parse_args
if "%~1"=="" goto args_done
if "%~1"=="--short" (
    set "SHORT=true"
    shift & goto parse_args
)
if "%~1"=="--help" goto show_help
if "%~1"=="-h" goto show_help
shift & goto parse_args

:show_help
echo Usage: %~nx0 [--short]
popd & endlocal & exit /b 0

:args_done

echo.
echo %BOLD%━━━ VietCropDoctor — Stack Status ━━━%NC%
echo.

:: ── Container status ──────────────────────────────────────────────────────────
echo %BOLD%Containers:%NC%
docker compose ps
echo.

if "!SHORT!"=="true" (
    popd & endlocal & exit /b 0
)

:: ── Resource usage ────────────────────────────────────────────────────────────
echo %BOLD%Resource Usage (CPU / RAM):%NC%
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
echo.

:: ── Health checks ─────────────────────────────────────────────────────────────
echo %BOLD%Health Checks:%NC%
echo.
echo   Service              URL                                      Status
echo   -------              ---                                      ------

call :check_svc "Gateway"       "http://localhost:8000/health"
call :check_svc "Vision-AI"     "http://localhost:8001/health"
call :check_svc "RAG Engine"    "http://localhost:8002/health"
call :check_svc "Analytics"     "http://localhost:8004/health"
call :check_svc "Auth"          "http://localhost:8005/health"
call :check_svc "Orchestrator"  "http://localhost:8006/health"
call :check_svc "MLflow"        "http://localhost:5000/health"
call :check_svc "Kafka UI"      "http://localhost:8080"
call :check_svc "MinIO"         "http://localhost:9001"
call :check_svc "Prometheus"    "http://localhost:9090/-/healthy"
call :check_svc "Grafana"       "http://localhost:3001/api/health"
call :check_svc "Airflow"       "http://localhost:8090/health"
call :check_svc "Qdrant"        "http://localhost:6333/healthz"
echo.

:: ── Port summary ──────────────────────────────────────────────────────────────
echo %BOLD%Port Bindings:%NC%
echo.
echo   Service         Port     Description
echo   -------         ----     -----------
echo   gateway         8000     API Gateway (Nginx^)
echo   vision-ai       8001     Vision AI service
echo   rag-engine      8002     RAG / vector search
echo   analytics       8004     Analytics service
echo   auth            8005     Auth / JWT service
echo   orchestrator    8006     Multi-agent orchestrator
echo   kafka           9092     Kafka broker
echo   qdrant          6333     Qdrant vector DB
echo   redis           6379     Redis cache
echo   postgres        5432     PostgreSQL
echo   clickhouse      8123     ClickHouse analytics DB
echo   ollama          11434    Ollama LLM server
echo   mlflow          5000     MLflow experiment tracking
echo   kafka-ui        8080     Kafka UI console
echo   minio           9001     MinIO console
echo   prometheus      9090     Prometheus metrics
echo   grafana         3001     Grafana dashboards
echo   airflow         8090     Airflow workflow UI
echo.

popd
endlocal
exit /b 0

:check_svc
setlocal
set "LABEL=%~1"
set "URL=%~2"
set "STATUS=000"
for /f %%s in ('curl -sf --max-time 3 -o nul -w "%%{http_code}" "%URL%" 2^>nul') do set "STATUS=%%s"
echo !STATUS! | findstr /R "^2" >nul 2>&1
if not errorlevel 1 (
    echo   %-20s %-40s %GREEN%OK (HTTP !STATUS!)%NC%
) else if "!STATUS!"=="000" (
    echo   %-20s %-40s %RED%OFFLINE%NC%
) else (
    echo   %-20s %-40s %YELLOW%HTTP !STATUS!%NC%
)
endlocal & goto :eof
