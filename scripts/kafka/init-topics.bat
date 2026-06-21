@echo off
:: kafka/init-topics.bat — Tạo 3 Kafka topics cho VietCropDoctor (Windows)
:: An toàn khi chạy nhiều lần.
::
:: Usage:
::   scripts\kafka\init-topics.bat
::   set PARTITIONS=6 && scripts\kafka\init-topics.bat
setlocal EnableDelayedExpansion

if not defined KAFKA_CONTAINER set "KAFKA_CONTAINER=vcd-kafka"
if not defined BOOTSTRAP       set "BOOTSTRAP=kafka:29092"
if not defined PARTITIONS      set "PARTITIONS=3"
if not defined REPLICATION     set "REPLICATION=1"

echo.
echo === Kafka Topic Initialisation ===
echo   Container  : %KAFKA_CONTAINER%
echo   Bootstrap  : %BOOTSTRAP%
echo   Partitions : %PARTITIONS% ^| Replication: %REPLICATION%
echo.

docker inspect --format="{{.State.Status}}" %KAFKA_CONTAINER% 2>nul | findstr "running" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Container '%KAFKA_CONTAINER%' không chạy.
    echo         Chạy: docker compose up -d kafka
    endlocal & exit /b 1
)

set "CREATED=0"
set "SKIPPED=0"
set "FAILED=0"

for %%T in (disease.detected chat.requested retrain.requested) do (
    docker exec %KAFKA_CONTAINER% kafka-topics --bootstrap-server %BOOTSTRAP% --list 2>nul | findstr /x "%%T" >nul 2>&1
    if not errorlevel 1 (
        echo   [!] %%T — đã tồn tại, bỏ qua
        set /a SKIPPED+=1
    ) else (
        docker exec %KAFKA_CONTAINER% kafka-topics ^
            --bootstrap-server %BOOTSTRAP% ^
            --create --if-not-exists ^
            --topic "%%T" ^
            --partitions %PARTITIONS% ^
            --replication-factor %REPLICATION% >nul 2>&1
        if not errorlevel 1 (
            echo   [OK] %%T ^(partitions=%PARTITIONS%^)
            set /a CREATED+=1
        ) else (
            echo   [FAIL] %%T
            set /a FAILED+=1
        )
    )
)

echo.
echo === Summary: created=!CREATED!  skipped=!SKIPPED!  failed=!FAILED! ===
echo.

if !FAILED! gtr 0 (
    endlocal & exit /b 1
)
endlocal
