---
title: Use MCP Chrome DevTools for dashboard testing instead of curl
type: decision
date: 2026-04-17
phase: testing
entity: dashboard
tags: [mcp, testing, browser, api]
status: invalidated
flag_reason: Superseded 2026-05-08: chrome-devtools-mcp caused periodic page reloads during testing in this repo and was uninstalled. Browser standard is now Playwright CLI — see browser-testing-use-playwright-cli-avoid-chrome-devtools-mcp
---

## Decision

Use MCP Chrome DevTools tools for all dashboard testing instead of curl or manual browser testing.

**Problems with curl:**
- PowerShell `curl` alias prompts for parameters (not agent-friendly)
- Requires complete request syntax (easy to miss params)
- Can't inspect browser state or UI elements

**Benefits of MCP Chrome DevTools:**
- Non-interactive, agent-friendly
- Inspect actual browser network requests: `list_network_requests` + `get_network_request`
- Take snapshots: `take_snapshot`
- Interact: click, fill forms, navigate
- Verify UI state matches API data

**Pattern:**
1. `list_pages()` → Find dashboard
2. `select_page(pageId=X)` → Select
3. `take_snapshot()` → See state
4. `click(uid=Y)` → Interact
5. `list_network_requests()` → See API calls
6. `get_network_request(reqid=Z)` → Inspect response

## Trace

- Inputs: Need to test dashboard Knowledge Base API and UI
- Policy: Use curl for API testing
- Exception: curl doesn't work on Windows (PowerShell alias), can't verify UI
- Approval: Switch to MCP Chrome DevTools for complete testing
- Outcome: Successfully tested API + UI, found and fixed bug showing 0 documents

## Agent Retrieval Summary

Retrieve this memory when working on dashboard, testing, or related decision changes. Use it to preserve the repo-local precedent: Decision Use MCP Chrome DevTools tools for all dashboard testing instead of curl or manual browser testing.

## User-Facing Summary

Decision Use MCP Chrome DevTools tools for all dashboard testing instead of curl or manual browser testing.

## Reusable Guidance

- Treat this as repo-local decision precedent for dashboard.
- Keep future implementation, docs, UI, and CLI behavior aligned with this memory.
- Prefer deterministic product evidence before changing or invalidating this guidance.

## When To Apply

Apply this when changes touch dashboard, the testing phase, or related tags: mcp, testing, browser, api.

## Retrieval Queries

- use mcp chrome devtools for dashboard testing instead of curl
- use mcp chrome devtools for dashboard testing instead of
- dashboard
- testing
- mcp
- browser
- api
