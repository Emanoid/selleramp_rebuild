@echo off
REM Build the Windows .exe bundle. Run from the repo root in cmd.exe.
SETLOCAL ENABLEDELAYEDEXPANSION

cd /d "%~dp0\.."

IF NOT EXIST .venv (
    py -3 -m venv .venv
)
call .venv\Scripts\activate.bat

pip install --upgrade pip wheel >NUL
pip install -e . streamlit pyinstaller >NUL

IF EXIST build\pyi_work rmdir /s /q build\pyi_work
IF EXIST dist\sa-rebuild rmdir /s /q dist\sa-rebuild

pyinstaller ^
    --noconfirm ^
    --workpath build\pyi_work ^
    --distpath dist ^
    sa-rebuild.spec

echo.
echo Built. Folder layout:
dir dist
echo.
echo Distribute the dist\sa-rebuild folder (zip it):
echo   powershell Compress-Archive -Path dist\sa-rebuild -DestinationPath dist\sa-rebuild-windows.zip
