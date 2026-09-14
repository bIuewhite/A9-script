@echo off
rem Open the desktop console (GUI).
rem ASCII-only on purpose: cmd.exe parses .bat with the system code page,
rem so Chinese text here would be garbled. All Chinese messages come from the
rem Python side. See the note in the one-click setup bat.
cd /d "%~dp0"

set "PYW="

rem 1) py launcher, windowless variant (pyw.exe ships with the launcher)
where pyw >nul 2>nul && set "PYW=pyw -3"

rem 2) pythonw.exe on PATH (skip the Microsoft Store stub)
if not defined PYW for /f "delims=" %%P in ('where pythonw 2^>nul ^| findstr /v /i "WindowsApps"') do if not defined PYW set "PYW=%%P"

rem 3) pythonw.exe next to whichever python.exe we can find
if not defined PYW for /f "delims=" %%P in ('where python 2^>nul ^| findstr /v /i "WindowsApps"') do if not defined PYW set "PYW=%%~dpPpythonw.exe"

if defined PYW (
    rem windowless: no black console window left behind
    start "" %PYW% "gui.py"
    exit /b 0
)

echo.
echo   [X] Python was not found on this computer.
echo.
echo       Please run the one-click setup bat first -- it installs Python
echo       and the dependencies for you.
echo.
echo       Or install Python 3.10+ from https://www.python.org/downloads/
echo       and tick BOTH boxes during setup:
echo          [x] Add python.exe to PATH
echo          [x] tcl/tk and IDLE
echo.
pause
exit /b 1
