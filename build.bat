@echo off
REM Build RepoReady into a standalone desktop app (dist\RepoReady.exe).
REM Requires Python 3.8+ on PATH.

setlocal

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Installing build dependencies...
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt pyinstaller

echo Building RepoReady.exe...
.venv\Scripts\pyinstaller --noconfirm --clean RepoReady.spec

echo.
echo Done. Your desktop app is at: dist\RepoReady.exe
endlocal