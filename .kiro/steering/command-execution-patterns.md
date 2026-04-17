---
inclusion: auto
---

# Command Execution - Friction Prevention

Prevents recurring friction: interactive commands, Windows compatibility, API testing, tool misuse.

## NEVER: Interactive Commands

❌ Block execution:
- `curl` without params → prompts
- `npm run dev`, `yarn start` → long-running
- `webpack --watch`, `jest --watch` → watchers
- `vim`, `nano`, `code` → editors

✅ Use:
- `curl -s "http://localhost:9876/api/kb/?scope=local"` (complete)
- Tell user to run dev servers manually
- `vitest --run`, `jest --no-watch` (non-interactive)
- `readFile`, `fsWrite` (Kiro tools)
- `controlPwshProcess` (long-running)

## Windows: Use Kiro Tools Over Shell

❌ Unix commands fail:
```bash
ls -la → Get-ChildItem or listDirectory
grep -r → Select-String or grepSearch
find . -name → fileSearch
cat file.txt → readFile
command1 && command2 → command1 ; command2
curl http://url → Invoke-WebRequest or use MCP browser tools
```

✅ Prefer Kiro tools: `listDirectory`, `grepSearch`, `readFile`, `fileSearch`
✅ For HTTP: Use MCP Chrome DevTools `mcp_chrome_devtools_get_network_request` to inspect API responses

## PowerShell curl Alias

❌ `curl http://127.0.0.1:9876/api/kb/?scope=global` → PowerShell alias prompts for Uri parameter
✅ `Invoke-WebRequest -Uri "http://127.0.0.1:9876/api/kb/?scope=global"` → Full PowerShell command
✅ Use MCP browser tools to inspect network requests instead

## File System Access Outside Workspace

❌ `listDirectory("C:/Users/user/.claude/knowledge")` → Access denied outside workspace
✅ `Get-ChildItem "$HOME/.claude/knowledge"` → PowerShell for paths outside workspace
✅ Use MCP browser network inspection to see API responses

## API: Complete Requests Only

❌ `curl http://localhost:9876/api/kb/` → prompts for params
✅ `curl -s "http://localhost:9876/api/kb/?scope=local"` → complete

Check server first: `curl -s http://localhost:9876/health`

## Workflow CLI: Direct Python

❌ `workflow summary <name>` → hangs on Windows
✅ `python $HOME/.claude/bin/workflow.py summary <name>`

Reason: PowerShell wrapper doesn't expand `$HOME` in Git Bash

## npm/npx: Full Path

❌ `npm install` → not in PATH
✅ `"/c/Program Files/nodejs/npm.cmd" install`

## Tests: Non-Interactive

❌ `pytest` → may hang with pdb
✅ `pytest --collect-only`, `pytest --tb=short`, `vitest --run`

## Quick Reference

Safe commands:
```bash
pytest --collect-only
ruff check .
curl -s "http://localhost:9876/api/kb/?scope=local"
python $HOME/.claude/bin/workflow.py memory list
```

Tell user to run manually:
```bash
python -m autonomous_agent_builder
cd frontend && npm run dev
builder start --port 9876
```
