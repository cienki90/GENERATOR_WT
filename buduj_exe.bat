@echo off
rem Buduje samodzielny program dist\Generator WT\Generator WT.exe (bez instalacji Pythona)
cd /d "%~dp0"
python -m pip install -r requirements.txt -r requirements-dev.txt -c constraints.txt
python -m pytest -q
if errorlevel 1 (
  echo Testy nie przeszly - program nie zostal zbudowany.
  pause
  exit /b 1
)
pyinstaller --noconfirm --windowed --name "Generator WT" --collect-all pyproj --collect-all pymupdf --collect-data docx --collect-data ezdxf --collect-submodules scipy.optimize --add-data "generator_wt\web\static;generator_wt\web\static" --exclude-module matplotlib --exclude-module tkinter uruchom.pyw
rem bez niepotrzebnych czesci Qt (QML, 3D, tlumaczenia, wersje debug) - ok. 250 MB mniej
python przytnij_exe.py "dist\Generator WT"
xcopy /E /I /Y szablony "dist\Generator WT\szablony"
mkdir "dist\Generator WT\dane" 2>nul
copy /Y dane\slowniki.xlsx "dist\Generator WT\dane\"
mkdir "dist\Generator WT\przyklady" 2>nul
copy /Y "przyklady\baza robocza.dxf" "dist\Generator WT\przyklady\"
copy /Y INSTRUKCJA.txt "dist\Generator WT\"
echo Gotowe: dist\Generator WT\Generator WT.exe
pause
