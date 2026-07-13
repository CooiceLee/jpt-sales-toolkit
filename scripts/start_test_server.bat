@echo off
setlocal

set ROOT_DIR=%~dp0..
cd /d "%ROOT_DIR%"

if "%JPT_DATA_DIR%"=="" set JPT_DATA_DIR=%ROOT_DIR%\data-test-server
if "%JPT_TEST_HOST%"=="" set JPT_TEST_HOST=0.0.0.0
if "%JPT_TEST_PORT%"=="" set JPT_TEST_PORT=8000

if not exist "%JPT_DATA_DIR%\attachments" mkdir "%JPT_DATA_DIR%\attachments"
if not exist "%JPT_DATA_DIR%\backups" mkdir "%JPT_DATA_DIR%\backups"
if not exist "%JPT_DATA_DIR%\imports" mkdir "%JPT_DATA_DIR%\imports"
if not exist "%JPT_DATA_DIR%\exports" mkdir "%JPT_DATA_DIR%\exports"

echo JPT Sales Toolkit v0.9.0 LAN test server
echo.
echo Data directory: %JPT_DATA_DIR%
echo Bind address:   %JPT_TEST_HOST%:%JPT_TEST_PORT%
echo.
echo Stop with Ctrl+C.
echo.

python run.py --host %JPT_TEST_HOST% --port %JPT_TEST_PORT% --data-dir "%JPT_DATA_DIR%" --no-browser
