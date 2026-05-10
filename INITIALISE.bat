@echo off
setlocal

set "SCRIPT_DIR=%~dp0"

where python >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
    goto :run
)

where python3 >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python3"
    goto :run
)

echo [ERREUR] Python 3 est requis et n'est pas dans le PATH.
echo Installez-le depuis https://www.python.org/downloads/
pause
exit /b 1

:run
"%PYTHON_CMD%" "%SCRIPT_DIR%INITIALISE.py" %*
exit /b %errorlevel%
