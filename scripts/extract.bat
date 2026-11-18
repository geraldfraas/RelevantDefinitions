@echo off
rem Builds data\definitions.json from nebraskalegislature.gov. Takes one to two hours.
rem Safe to close and run again: finished downloads are kept.
cd /d "%~dp0.."
if exist data\definitions.json copy /y data\definitions.json data\definitions.previous.json >nul
python scripts\extract_definitions.py all
echo.
python scripts\validate_definitions.py
echo.
pause
