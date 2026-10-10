@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\setup.ps1"
if errorlevel 1 pause
