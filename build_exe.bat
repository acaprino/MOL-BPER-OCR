@echo off
setlocal
cd /d "%~dp0"

rem ============================================================
rem Build del pacchetto portable EdgeAgent (PyInstaller onedir)
rem Output: dist\EdgeAgent  (da zippare per la consegna)
rem ============================================================

rem --- Assicura Python (3.13 o 3.12), installandolo se assente ---
set "PY_CMD="
py -3.13 -c "pass" >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -3.13"
if defined PY_CMD goto have_python
py -3.12 -c "pass" >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -3.12"
if defined PY_CMD goto have_python

echo [INFO] Python non trovato: provo l'installazione automatica via winget...
winget install -e --id Python.Python.3.13 --silent --accept-package-agreements --accept-source-agreements
py -3.13 -c "pass" >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -3.13"
if defined PY_CMD goto have_python

echo [INFO] winget non riuscito: scarico l'installer ufficiale di Python...
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.13.5/python-3.13.5-amd64.exe' -OutFile \"$env:TEMP\python-setup.exe\""
if errorlevel 1 goto no_python
"%TEMP%\python-setup.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1
py -3.13 -c "pass" >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -3.13"
if defined PY_CMD goto have_python

:no_python
echo [ERRORE] Python non disponibile e installazione automatica fallita.
echo          Se l'installazione e' appena terminata, riapri il terminale e rilancia.
exit /b 1

:have_python
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Creo l'ambiente virtuale e installo le dipendenze...
    %PY_CMD% -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERRORE] Installazione dipendenze fallita.
        exit /b 1
    )
)

".venv\Scripts\python.exe" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installo PyInstaller nel venv...
    ".venv\Scripts\python.exe" -m pip install pyinstaller
    if errorlevel 1 exit /b 1
)

rem Pulizia della build precedente: evita residui nel pacchetto finale
rem (cache pesi scaricata nei test, .env con chiave reale, file orfani).
if exist "dist\EdgeAgent" rmdir /s /q "dist\EdgeAgent" 2>nul
if exist "dist\EdgeAgent" (
    echo [ERRORE] dist\EdgeAgent e' in uso da un altro processo: chiudi EdgeAgent e rilancia.
    exit /b 1
)

rem Guardia segreti: mai spedire una api_key scritta nell'INI (finirebbe nello
rem zip in 2 copie, una invisibile dentro _internal). Vale anche per i REDACTED.
findstr /r /c:"^api_key *= *[^ ]" "edge-agent\config.ini" >nul 2>&1
if not errorlevel 1 (
    echo [ERRORE] edge-agent\config.ini contiene una api_key valorizzata:
    echo          svuotala prima di creare il pacchetto.
    exit /b 1
)

echo [INFO] Build EdgeAgent in corso (alcuni minuti: include torch)...
".venv\Scripts\python.exe" -m PyInstaller edge_agent.spec --noconfirm
if errorlevel 1 (
    echo [ERRORE] Build PyInstaller fallita.
    exit /b 1
)

echo [INFO] Copio config, prompt e asset nella cartella portable...
copy /y "edge-agent\config.ini" "dist\EdgeAgent\config.ini" >nul
xcopy /e /i /y "edge-agent\assets" "dist\EdgeAgent\assets" >nul
rem Prompt LLM modificabili senza rebuild: questa copia ha la precedenza sul bundle.
rem Solo i .json: la cartella sorgente non deve poter spedire altri file nello zip.
if not exist "dist\EdgeAgent\prompts" mkdir "dist\EdgeAgent\prompts"
copy /y "prompts\*.json" "dist\EdgeAgent\prompts" >nul

rem Template .env SENZA chiave (fonte unica: edge-agent\defaults\env.template);
rem la chiave viene chiesta al primo avvio.
copy /y "edge-agent\defaults\env.template" "dist\EdgeAgent\.env" >nul

echo [INFO] Creo lo zip finale (puo' richiedere qualche minuto)...
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set BUILD_DATE=%%i
powershell -NoProfile -Command "Compress-Archive -Path 'dist\EdgeAgent' -DestinationPath 'dist\EdgeAgent_%BUILD_DATE%.zip' -Force"
if errorlevel 1 (
    echo [ERRORE] Creazione zip fallita.
    exit /b 1
)

echo.
echo [OK] Pacchetto finale pronto: dist\EdgeAgent_%BUILD_DATE%.zip
echo      Consegnalo cosi' com'e': al primo avvio scarica i componenti AI
echo      e chiede la chiave API.
endlocal
