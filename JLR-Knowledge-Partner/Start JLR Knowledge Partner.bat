@echo off
rem JLR Knowledge Partner: installs what is missing (first run) and starts the app.
title JLR Knowledge Partner
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run.ps1"
