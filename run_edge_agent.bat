@echo off
REM ============================================================
REM  Edge Agent launcher (Windows)
REM  - Creates a local virtual environment (.venv) on first run
REM  - Installs dependencies from requirements.txt
REM  - Launches the PyQt6 edge client (edge-agent\edge_agent.py)
REM
REM  Any arguments are forwarded to the app, e.g.:
REM      run_edge_agent.bat --debug
REM ============================================================
setlocal

set "ROOT=%~dp0"
set "VENV_DIR=%ROOT%.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "REQS=%ROOT%requirements.txt"
set "ENTRY=%ROOT%edge-agent\edge_agent.py"

REM --- Create the virtual environment on first run ------------
if not exist "%VENV_PY%" (
    echo [edge-agent] Virtual environment not found. Creating it in "%VENV_DIR%"...
    call :make_venv || exit /b 1
)

REM --- Launch the edge client ---------------------------------
echo [edge-agent] Starting Edge Agent...
"%VENV_PY%" "%ENTRY%" %*
exit /b %errorlevel%

REM ============================================================
:make_venv
REM Prefer the Windows "py" launcher, fall back to "python" on PATH.
py -3 -m venv "%VENV_DIR%" >nul 2>nul
if not exist "%VENV_PY%" python -m venv "%VENV_DIR%"
if not exist "%VENV_PY%" (
    echo [edge-agent] ERROR: could not create the virtual environment.
    echo               Install Python 3.8+ from https://www.python.org/downloads/ and retry.
    exit /b 1
)
echo [edge-agent] Installing dependencies ^(first run only; torch is large, this may take several minutes^)...
"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install -r "%REQS%"
if errorlevel 1 (
    echo [edge-agent] ERROR: dependency installation failed.
    echo               Delete "%VENV_DIR%" and retry.
    exit /b 1
)
exit /b 0
