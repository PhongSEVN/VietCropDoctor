@echo off
:: ml/ingest-knowledge.bat — Chạy pipeline ingest tài liệu vào Qdrant (Windows)
::
:: Usage:
::   scripts\ml\ingest-knowledge.bat
::   scripts\ml\ingest-knowledge.bat --crop lua
::   scripts\ml\ingest-knowledge.bat --crop ca-phe
::   scripts\ml\ingest-knowledge.bat --rebuild
::
:: Yêu cầu:
::   docker compose up -d qdrant rag-engine
setlocal EnableDelayedExpansion
chcp 65001 >nul

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\.."
set "RAG_URL=http://localhost:8002"
set "KNOWLEDGE_DIR=rag/knowledge"

set "CROP="
set "REBUILD=false"

:parse
if "%~1"=="" goto done_parse
if /i "%~1"=="--crop"    (set "CROP=%~2"     & shift & shift & goto parse)
if /i "%~1"=="--rebuild" (set "REBUILD=true" & shift          & goto parse)
if /i "%~1"=="--help"    goto show_help
if /i "%~1"=="-h"        goto show_help
shift & goto parse

:show_help
echo Usage: %~nx0 [--crop ^<name^>] [--rebuild]
echo   --crop ^<name^>   Ingest chỉ cây này: lua, ca-phe, mia, ngo
echo   --rebuild        Xoá collection cũ, ingest lại từ đầu
endlocal & exit /b 0

:done_parse

echo.
echo === VietCropDoctor — Knowledge Ingestion ===
echo.

curl -sf http://localhost:6333/healthz >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Qdrant không chạy tại http://localhost:6333
    echo         Chạy: docker compose up -d qdrant
    endlocal & exit /b 1
)
echo [OK]   Qdrant reachable

:: Ingestion đi qua RAG engine HTTP API (POST /ingest, /reindex) — chạy pipeline
:: local thật và rebuild BM25 index, nên engine bắt buộc phải đang chạy.
curl -sf %RAG_URL%/health >nul 2>&1
if errorlevel 1 (
    echo [ERROR] RAG engine không chạy tại %RAG_URL%
    echo         Chạy: docker compose up -d rag-engine
    endlocal & exit /b 1
)
echo [OK]   RAG engine reachable

if "!REBUILD!"=="true" (
    echo [INFO] Rebuild: xoá collection và ingest lại toàn bộ %KNOWLEDGE_DIR%...
    curl -fsS -X POST %RAG_URL%/reindex
    goto check_result
)

if defined CROP (
    set "DIR="
    if /i "!CROP!"=="lua"    set "DIR=rag/knowledge/lúa"
    if /i "!CROP!"=="ca-phe" set "DIR=rag/knowledge/cà phê"
    if /i "!CROP!"=="mia"    set "DIR=rag/knowledge/mía"
    if /i "!CROP!"=="ngo"    set "DIR=rag/knowledge/ngô"
    if not defined DIR (
        echo [ERROR] Crop không hợp lệ: !CROP! ^(hợp lệ: lua, ca-phe, mia, ngo^)
        endlocal & exit /b 1
    )
    echo [INFO] Ingesting crop !CROP! từ "!DIR!"...
    curl -fsS -X POST %RAG_URL%/ingest -H "Content-Type: application/json" -d "{\"directory\": \"!DIR!\", \"recreate_collection\": false}"
    goto check_result
)

echo [INFO] Ingesting toàn bộ %KNOWLEDGE_DIR%...
curl -fsS -X POST %RAG_URL%/ingest -H "Content-Type: application/json" -d "{\"directory\": \"rag/knowledge\", \"recreate_collection\": false}"

:check_result
if errorlevel 1 (
    echo [ERROR] Ingestion thất bại.
    endlocal & exit /b 1
)
echo.
echo [OK]   Ingestion xong.
echo        Kiểm tra: curl http://localhost:6333/collections
endlocal
