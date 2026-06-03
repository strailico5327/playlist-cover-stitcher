@echo off
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
python -m playlist_cover_stitcher
if errorlevel 1 pause
