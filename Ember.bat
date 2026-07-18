@echo off
rem Dev launcher: windowless via pyw if available, console fallback via py
rem so errors are visible instead of silently vanishing.
cd /d "%~dp0"

where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw -3.11 qt_main.py
) else (
    py -3.11 qt_main.py
)
