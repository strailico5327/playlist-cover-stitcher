@echo off
cd /d "%~dp0"
python playlist_cover_stitcher.py
if errorlevel 1 pause
