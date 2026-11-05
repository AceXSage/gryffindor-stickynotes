@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto USE_VENV
where py >nul 2>nul
if errorlevel 1 goto TRY_PYTHON
py -3 -c "import PyQt5" >nul 2>nul
if errorlevel 1 goto TRY_PYTHON
py -3 "%~dp0Gryffindor.py"
if errorlevel 2 goto ALREADY
goto END
:TRY_PYTHON
where python >nul 2>nul
if errorlevel 1 goto NO_PY
python -c "import PyQt5" >nul 2>nul
if errorlevel 1 goto NO_PYQT
python "%~dp0Gryffindor.py"
if errorlevel 2 goto ALREADY
goto END
:USE_VENV
".venv\Scripts\python.exe" "%~dp0Gryffindor.py"
if errorlevel 2 goto ALREADY
goto END
:ALREADY
echo.
echo Gryffindor is already running - exit it from the tray icon first.
echo.
pause
goto END
:NO_PY
echo [ERROR] Python not found on PATH.
echo   Install Python 3.8+ and tick "Add python.exe to PATH", then run this again.
goto END
:NO_PYQT
echo [ERROR] PyQt5 is not installed for this Python.
echo   1. python -m venv .venv
echo   2. .venv\Scripts\activate
echo   3. pip install PyQt5 -i https://pypi.tuna.tsinghua.edu.cn/simple
echo   4. double-click run.cmd again
:END
endlocal
