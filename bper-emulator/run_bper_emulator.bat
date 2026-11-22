@echo off
REM ============================================================
REM  BPER emulator launcher (Windows)
REM  - Uses the repo .venv Python when present, else py -3.13 / -3.12
REM  - Starts the local server and opens the browser on it
REM  - The server needs only the standard library; Pillow is needed
REM    only for --include-reference
REM
REM  Any arguments are forwarded to the server, e.g.:
REM      run_bper_emulator.bat --include-reference
REM      run_bper_emulator.bat --export Simulatore-BPER.html
REM      run_bper_emulator.bat --port 8800
REM ============================================================
setlocal

set "HERE=%~dp0"
set "SERVER=%HERE%serve_bper_simulator.py"
set "URL=http://127.0.0.1:8765/"

REM --- Pick a Python that actually starts ----------------------
set PYCMD="%HERE%..\.venv\Scripts\python.exe"
%PYCMD% -c "pass" >nul 2>nul
if not errorlevel 1 goto have_python
set PYCMD=py -3.13
%PYCMD% -c "pass" >nul 2>nul
if not errorlevel 1 goto have_python
set PYCMD=py -3.12
%PYCMD% -c "pass" >nul 2>nul
if not errorlevel 1 goto have_python
echo [bper-emulator] Python non trovato: serve .venv oppure py -3.13 / py -3.12.
pause
exit /b 1

:have_python
REM --- Open the browser only for the default run ---------------
REM With arguments (--port, --export, ...) the URL may differ or the
REM server may not start, so nothing is opened.
if "%~1"=="" start "" /min cmd /c "ping -n 3 127.0.0.1 >nul & start %URL%"

echo [bper-emulator] Avvio del simulatore: %URL%  (Ctrl+C per uscire)
%PYCMD% "%SERVER%" %*
set "CODE=%errorlevel%"
if not "%CODE%"=="0" pause
exit /b %CODE%
