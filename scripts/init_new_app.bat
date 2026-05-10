@echo off
REM ============================================================
REM Script d'initialisation d'une nouvelle application HUB
REM ============================================================
REM Usage: scripts\init_new_app.bat
REM        scripts\init_new_app.bat --clean
REM        scripts\init_new_app.bat --tailwind
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo ========================================================
echo   Initialisation d'une nouvelle application HUB
echo ========================================================
echo.

REM Trouver le répertoire du script
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

REM Vérifier Python
where python >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
    goto :check_version
)

where python3 >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python3"
    goto :check_version
)

echo [ERREUR] Python n'est pas installe ou n'est pas dans le PATH.
echo Veuillez installer Python 3.6+ depuis https://www.python.org/downloads/
echo.
pause
exit /b 1

:check_version
REM Vérifier la version de Python
for /f "tokens=*" %%i in ('%PYTHON_CMD% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PYTHON_VERSION=%%i

echo [OK] Python %PYTHON_VERSION% detecte
echo.

REM Aller dans le répertoire du projet
cd /d "%PROJECT_ROOT%"

REM Deleguer vers le nouveau lanceur racine
%PYTHON_CMD% "%PROJECT_ROOT%\INITIALISE.py" %*

if %errorlevel% neq 0 (
    echo.
    echo [ERREUR] Le script a rencontre une erreur.
    pause
    exit /b 1
)

echo.
pause
