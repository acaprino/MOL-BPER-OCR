@echo off
REM ============================================================
REM  Edge Agent launcher (Windows)
REM  - Self-heals a broken/stale .venv (e.g. base Python moved)
REM  - Creates .venv on first run and installs requirements.txt
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

REM --- Drop a stale venv whose base interpreter is gone -------
REM A venv records an absolute path to the Python it was built from.
REM If that interpreter is moved or uninstalled, .venv\Scripts\python.exe
REM still exists but fails at startup. Probe it and rebuild if dead.
if exist "%VENV_PY%" (
    "%VENV_PY%" -c "pass" >nul 2>nul
    if errorlevel 1 (
        echo [edge-agent] Existing .venv is broken ^(base Python missing^); rebuilding it...
        rmdir /s /q "%VENV_DIR%"
    )
)

REM --- Create the virtual environment when missing -----------
if not exist "%VENV_PY%" (
    echo [edge-agent] Creating virtual environment in "%VENV_DIR%"...
    call :make_venv || exit /b 1
)

REM --- Launch the edge client --------------------------------
echo [edge-agent] Starting Edge Agent...
"%VENV_PY%" "%ENTRY%" %*
exit /b %errorlevel%

REM ============================================================
:make_venv
REM Pick a base interpreter. Prefer 3.13 (the project's known-good
REM runtime, with full torch / PyQt6 wheel coverage), then 3.12, then
REM whatever "python" resolves to. We deliberately avoid a bare
REM "py -3", which selects the newest install (e.g. 3.14) that often
REM has no torch wheels yet.
set "BASE="
py -3.13 -c "pass" >nul 2>nul && set "BASE=py -3.13"
if defined BASE goto :base_ready
py -3.12 -c "pass" >nul 2>nul && set "BASE=py -3.12"
if defined BASE goto :base_ready
python -c "pass" >nul 2>nul && set "BASE=python"
if defined BASE goto :base_ready
echo [edge-agent] ERROR: no suitable Python found ^(need 3.12 or 3.13^).
echo               Install one from https://www.python.org/downloads/ and retry.
exit /b 1

:base_ready
echo [edge-agent] Using base interpreter: %BASE%
%BASE% -m venv "%VENV_DIR%"
if not exist "%VENV_PY%" (
    echo [edge-agent] ERROR: could not create the virtual environment with "%BASE%".
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
