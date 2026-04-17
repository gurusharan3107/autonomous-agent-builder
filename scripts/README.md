# Development Scripts

## Dashboard Deployment

After making changes to the frontend, use this script to build and deploy:

### Windows (PowerShell)
```powershell
./scripts/deploy_dashboard.ps1
```

### Linux/Mac (Bash)
```bash
./scripts/deploy_dashboard.sh
```

### Windows (Batch)
```cmd
scripts\deploy_dashboard.bat
```

This script will:
1. Build the frontend (`npm run build`)
2. Copy the built files to `.agent-builder/dashboard/`
3. Notify you to refresh your browser

**Note**: The server doesn't need to be restarted - just refresh your browser with `Ctrl+Shift+R` (hard refresh).
