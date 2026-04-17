---
inclusion: auto
---

# Server Management

## Check Before Start

```bash
Get-NetTCPConnection -LocalPort 9876 -ErrorAction SilentlyContinue
listProcesses
```

## Restart

1. Stop: `controlPwshProcess action=stop terminalId=X`
2. Start: `controlPwshProcess action=start command="builder start --port 9876"`
3. Verify: `getProcessOutput terminalId=Y lines=20`

## Deploy

`./scripts/deploy_dashboard.ps1` builds frontend only, doesn't restart server.

**After code changes:**
1. `./scripts/deploy_dashboard.ps1`
2. Stop + start server
3. Refresh browser

## Ports

| Port | Service | Command |
|------|---------|---------|
| 8000 | Main API | `python -m autonomous_agent_builder` |
| 9876 | Dashboard | `builder start --port 9876` |
| 5173 | Frontend dev | `cd frontend && npm run dev` |
