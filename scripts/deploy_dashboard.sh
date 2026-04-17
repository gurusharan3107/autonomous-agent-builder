#!/bin/bash
# Quick dashboard deployment script

echo "Building frontend..."
cd frontend && npm run build && cd ..

echo "Deploying to dashboard..."
rm -rf .agent-builder/dashboard/*
cp -r frontend/dist/* .agent-builder/dashboard/

echo "✓ Dashboard deployed! Refresh your browser (Ctrl+Shift+R)"
