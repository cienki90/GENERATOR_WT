@echo off
rem Buduje samodzielny program dist\Generator WT\Generator WT.exe (bez instalacji Pythona)
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --windowed --name "Generator WT" --collect-all pyproj --collect-data docx --collect-data ezdxf --collect-submodules scipy.optimize --exclude-module matplotlib --exclude-module tkinter uruchom.pyw
xcopy /E /I /Y szablony "dist\Generator WT\szablony"
mkdir "dist\Generator WT\dane" 2>nul
copy /Y dane\slowniki.xlsx "dist\Generator WT\dane\"
mkdir "dist\Generator WT\przyklady" 2>nul
copy /Y "przyklady\baza robocza.dxf" "dist\Generator WT\przyklady\"
copy /Y INSTRUKCJA.txt "dist\Generator WT\"
echo Gotowe: dist\Generator WT\Generator WT.exe
pause
