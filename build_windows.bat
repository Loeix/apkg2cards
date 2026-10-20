@echo off
REM Construit l'application Windows (dist\apkg2cards\apkg2cards.exe)
REM puis l'installateur (installer\apkg2cards-setup.exe) si Inno Setup est installe.
setlocal
cd /d "%~dp0"

python -m pip install -r requirements.txt pyinstaller || goto :err

python -m PyInstaller --noconfirm --clean --windowed --name apkg2cards ^
  --icon assets\icon.ico --exclude-module tkinter --collect-submodules apkg2cards run_gui.py || goto :err

set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
  for /f %%v in ('python packaging\get_version.py') do set VERSION=%%v
  %ISCC% /DMyAppVersion=%VERSION% packaging\installer.iss || goto :err
  echo.
  echo Installateur : installer\apkg2cards-setup.exe
) else (
  echo.
  echo Application : dist\apkg2cards\apkg2cards.exe
  echo Pour creer l'installateur, installe Inno Setup 6 ^(jrsoftware.org^) puis relance ce script.
)
exit /b 0

:err
echo Erreur pendant la construction.
exit /b 1
