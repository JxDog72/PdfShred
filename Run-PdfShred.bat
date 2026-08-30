@echo off
title PdfShred
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo Python 3.10+ was not found on PATH.
        echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
        pause
        exit /b 1
    )
    set "PY=py"
) else (
    set "PY=python"
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

%PY% app.py %*
if errorlevel 1 (
    echo.
    echo PdfShred failed to start. See the message above.
    pause
)
