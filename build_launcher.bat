@echo off
rem Rebuild the exe launchers. Needs Python (see README).
rem ASCII-only on purpose - see the note in the one-click setup bat.
cd /d "%~dp0"

py -3 "build_launcher.py" 2>nul
if errorlevel 1 python "build_launcher.py"
pause
