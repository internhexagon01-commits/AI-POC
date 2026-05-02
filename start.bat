@echo off
cd /d "%~dp0"
echo Starting NovAtel Agent UI...
uv run src/ui_server.py
pause
