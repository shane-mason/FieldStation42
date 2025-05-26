@echo off
set MODE=docker
set ENV_FILE=.env

echo Installing Fieldstation 42 in Docker...

REM Check Python availability
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not on PATH
    exit /b 1
)

REM Install the CLI
pip install -e .

REM Write FIELDSTATION_MODE to .env
(for /f "tokens=1* delims=:" %%a in ('findstr /b /c:"FIELDSTATION_MODE=" %ENV_FILE% 2^>nul') do (
    echo FIELDSTATION_MODE=%MODE%
) || (
    echo FIELDSTATION_MODE=%MODE% >> %ENV_FILE%
))

REM Detect WSL
ver | findstr /i "microsoft" >nul
if %errorlevel%==0 (
    set DOCKER_ENV_FILE=docker/.env.wsl
    echo Detected WSL — using %DOCKER_ENV_FILE%
) else (
    set DOCKER_ENV_FILE=docker/.env.linux
    echo Detected native Windows — using %DOCKER_ENV_FILE%
)

REM Launch Docker
docker compose --env-file %DOCKER_ENV_FILE% up --build -d
if %errorlevel% neq 0 (
    echo [ERROR] Docker Compose failed to start.
    exit /b 1
)

echo Docker containers are now running.
echo You can now run:
echo   fs42 station_42 --args
