@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo This removes only the local SQLite demo database and files generated under storage\demo-uploads.
echo It permanently deletes the demo account, business, documents, reconciliation and audit data.
choice /C YN /N /M "Continue with demo data reset? [Y/N] "
if errorlevel 2 (
  echo Reset cancelled. Existing data was preserved.
  exit /b 0
)
call "%~dp0stop-ledgerpilot.bat"
if exist "backend\storage\ledgerpilot-demo.sqlite3" del /F "backend\storage\ledgerpilot-demo.sqlite3"
if exist "backend\storage\ledgerpilot-demo.sqlite3-wal" del /F "backend\storage\ledgerpilot-demo.sqlite3-wal"
if exist "backend\storage\ledgerpilot-demo.sqlite3-shm" del /F "backend\storage\ledgerpilot-demo.sqlite3-shm"
if exist "storage\demo-uploads" rmdir /S /Q "storage\demo-uploads"
echo Demo data removed. Run setup-and-run.bat to create a fresh synthetic workspace.
