@echo off
cd /d "%~dp0"

set "PY="
set "PYW="
where python >nul 2>nul && set "PY=python"
where pythonw >nul 2>nul && set "PYW=pythonw"
if not defined PY (
    where py >nul 2>nul && set "PY=py"
)
if not defined PYW (
    where pyw >nul 2>nul && set "PYW=pyw"
)
if not defined PY (
    echo Python 3.10+ was not found on PATH.
    echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
    pause
    exit /b 1
)

%PY% -c "import customtkinter, fitz, PIL" 1>nul 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Could not install packages. Try:  %PY% -m pip install -r requirements.txt
        pause
        exit /b 1
    )
)

REM Windows OCR is optional. Skip quietly if WinRT is unavailable.
%PY% -c "import winocr" 1>nul 2>nul
if errorlevel 1 (
    %PY% -m pip install winocr 1>nul 2>nul
)

if defined PYW (
    start "" %PYW% app.py %*
    exit /b 0
)

%PY% app.py %*
if errorlevel 1 (
    echo.
    echo PdfShred failed to start. See the message above.
    pause
)
