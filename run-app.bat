@echo off
REM Starts TexTailor: backend (FastAPI :8000) + frontend (Angular :4200) via start.ps1.
REM Opens a Windows Terminal window with 2 separate tabs (BACKEND, FRONTEND) that stay open.
cd /d "D:\AI resume automater"
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\AI resume automater\start.ps1"
pause
