@echo off
setlocal
set "taskPython=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%taskPython%" set "taskPython=%~dp0runtime\pythonw.exe"
if not exist "%taskPython%" (
  echo Project Python environment is missing. Please run Install.ps1 first.
  pause
  exit /b 1
)
start "" "%taskPython%" "%~dp0BackendControl.pyw"
