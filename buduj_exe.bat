@echo off
rem Buduje samodzielny program dist\Generator WT\Generator WT.exe (bez instalacji Pythona)
cd /d "%~dp0"
python -m pip install pyinstaller
pyinstaller --noconfirm --windowed --name "Generator WT" uruchom.pyw
xcopy /E /I /Y szablony "dist\Generator WT\szablony"
xcopy /E /I /Y dane "dist\Generator WT\dane"
echo Gotowe: dist\Generator WT\Generator WT.exe
pause
