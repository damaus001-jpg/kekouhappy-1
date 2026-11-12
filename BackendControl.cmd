@echo off
setlocal
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo Project Python environment is missing. Please run Install.ps1 first.
  pause
  exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0BackendControl.pyw"
