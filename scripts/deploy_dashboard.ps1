#!/usr/bin/env pwsh
# Quick dashboard deployment script

Write-Host "Building frontend..." -ForegroundColor Cyan
Set-Location frontend
npm run build
Set-Location ..

Write-Host "Deploying to dashboard..." -ForegroundColor Cyan
Remove-Item -Recurse -Force .agent-builder/dashboard/* -ErrorAction SilentlyContinue
Copy-Item -Recurse -Force frontend/dist/* .agent-builder/dashboard/

Write-Host "Dashboard deployed! Refresh your browser" -ForegroundColor Green
