@echo off
setlocal
echo Stopping LedgerPilot API and frontend console windows...
taskkill /F /T /FI "WINDOWTITLE eq LedgerPilot API*" >nul 2>&1
taskkill /F /T /FI "WINDOWTITLE eq LedgerPilot Web*" >nul 2>&1
echo Stop request sent. If an application was started manually, stop it in its terminal.
