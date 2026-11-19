@echo off
cd /d "%~dp0"
set "PYTHON_EXE="
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
    if exist "%%~D\python.exe" set "PYTHON_EXE=%%~D\python.exe"
)
if defined PYTHON_EXE (
    "%PYTHON_EXE%" -m pip install -q -r requirements.txt
    "%PYTHON_EXE%" kernel_app.py
) else (
    python -m pip install -q -r requirements.txt
    python kernel_app.py
)
if errorlevel 1 pause
