@echo off
rem IPGuard Windows build script: produces dist\IPGuard.exe (single file, no console)
setlocal
cd /d "%~dp0\.."

echo [1/4] Creating build virtualenv...
python -m venv .venv-build
call .venv-build\Scripts\activate.bat
pip install -q -U pip
pip install -q -r requirements.txt pyinstaller pillow

echo [2/4] Generating app icon...
python packaging\make_icon.py

echo [3/4] PyInstaller bundle...
pyinstaller --noconfirm --clean --onefile --windowed --name IPGuard --icon build\icon.ico main.py

echo [4/4] Done: dist\IPGuard.exe
echo Note: unsigned binaries may trigger SmartScreen on first run; choose "More info - Run anyway".
endlocal
