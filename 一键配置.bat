@echo off
rem ============================================================
rem  One-click environment setup.
rem  (This file is ASCII-only on purpose: cmd.exe parses .bat with the
rem   system code page, so Chinese text here would be garbled. All
rem   Chinese messages are printed by setup_env.py instead.)
rem
rem  What it does:
rem    1) find Python
rem    2) hand over to setup_env.py (installs deps, runs the health check)
rem ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PY="

rem ---- 1) the "py" launcher (most reliable) ----
for /f "delims=" %%P in ('where py 2^>nul') do (
    if not defined PY set "PY=%%P -3"
)

rem ---- 2) python.exe on PATH (skip the Microsoft Store stub) ----
if not defined PY (
    for /f "delims=" %%P in ('where python 2^>nul ^| findstr /v /i "WindowsApps"') do (
        if not defined PY set "PY=%%P"
    )
)

rem ---- 3) usual install locations ----
if not defined PY (
    for %%D in (
        "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
        "%LOCALAPPDATA%\Python\pythoncore-3.13-64\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
        "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
        "C:\Python314\python.exe"
        "C:\Python313\python.exe"
        "C:\Python312\python.exe"
    ) do (
        if not defined PY if exist %%D set "PY=%%D"
    )
)

if not defined PY (
    echo.
    echo   [X] Python was not found on this computer.
    echo.
    echo       This project needs Python 3.10 or newer.
    echo       Opening the download page for you ...
    echo.
    echo       During installation, please tick BOTH boxes:
    echo          [x] Add python.exe to PATH
    echo          [x] tcl/tk and IDLE
    echo.
    echo       After that, run this file again.
    echo.
    start "" "https://www.python.org/downloads/"
    pause
    exit /b 1
)

echo   Using Python: %PY%
echo.
%PY% "setup_env.py"
echo.
pause
exit /b 0
