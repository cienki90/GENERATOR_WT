@echo off
cd /d "%~dp0"
echo Instalacja bibliotek programu Generator WT...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Gotowe. Program uruchomisz plikiem "Generator WT.bat".
pause
