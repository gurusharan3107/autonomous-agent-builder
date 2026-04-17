@echo off
REM Quick dashboard deployment script for Windows

echo Building frontend...
cd frontend
call npm run build
cd ..

echo Deploying to dashboard...
rmdir /s /q .agent-builder\dashboard
xcopy /E /I /Y frontend\dist .agent-builder\dashboard

echo.
echo ✓ Dashboard deployed! Refresh your browser (Ctrl+Shift+R)
