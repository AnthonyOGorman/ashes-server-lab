@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0CPP\tools\Start-Client.ps1"
if errorlevel 1 pause
