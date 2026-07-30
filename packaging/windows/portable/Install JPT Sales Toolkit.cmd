@echo off
setlocal EnableExtensions

rem Resolve the package root without a trailing backslash. Robocopy can merge
rem the next quoted argument when a quoted source path ends in a backslash.
for %%I in ("%~dp0.") do set "JPT_SOURCE=%%~fI"

if not defined LOCALAPPDATA (
  echo LOCALAPPDATA is not available for the current Windows account.
  pause
  exit /b 2
)

set "JPT_TARGET=%LOCALAPPDATA%\Programs\JPT Sales Toolkit"
set "JPT_DATA_DIR=%LOCALAPPDATA%\JPT Sales Toolkit\data"

if not exist "%JPT_SOURCE%\runtime\pythonw.exe" (
  echo This portable package is incomplete: runtime\pythonw.exe was not found.
  pause
  exit /b 3
)

if not exist "%JPT_SOURCE%\app\desktop_launcher.py" (
  echo This portable package is incomplete: app\desktop_launcher.py was not found.
  pause
  exit /b 4
)

if not exist "%JPT_TARGET%" (
  mkdir "%JPT_TARGET%"
  if errorlevel 1 (
    echo Unable to create "%JPT_TARGET%".
    pause
    exit /b 5
  )
)

if /I "%JPT_SOURCE%"=="%JPT_TARGET%" goto create_shortcuts

where robocopy.exe >nul 2>&1
if errorlevel 1 goto copy_with_xcopy

robocopy "%JPT_SOURCE%" "%JPT_TARGET%" /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /XJ /NFL /NDL /NJH /NJS /NP
set "JPT_COPY_RESULT=%ERRORLEVEL%"
if %JPT_COPY_RESULT% GEQ 8 goto copy_failed
goto create_shortcuts

:copy_with_xcopy
xcopy "%JPT_SOURCE%\*" "%JPT_TARGET%" /E /I /H /K /Y /Q
if errorlevel 1 goto copy_failed
goto create_shortcuts

:copy_failed
echo JPT program files could not be copied to "%JPT_TARGET%".
echo Existing user data was not removed.
pause
exit /b 6

:create_shortcuts
cscript.exe //nologo "%JPT_TARGET%\tools\Create-JPT-Shortcuts.vbs" "%JPT_TARGET%"
if errorlevel 1 (
  echo JPT was copied, but one or more current-user shortcuts could not be created.
  echo You can start it from "%JPT_TARGET%\Start JPT Sales Toolkit.cmd".
) else (
  echo Current-user desktop and Start Menu shortcuts were created.
)

echo.
echo JPT Sales Toolkit 0.11.7-internal portable test fallback is installed at:
echo   %JPT_TARGET%
echo Existing data remains at:
echo   %JPT_DATA_DIR%
echo.

call "%JPT_TARGET%\Start JPT Sales Toolkit.cmd"
exit /b %ERRORLEVEL%
