---
title: Browser testing — use Playwright CLI; avoid Chrome DevTools MCP
type: correction
date: 2026-05-08
phase: testing
entity: browser-testing
tags: [browser-testing, playwright, chrome-devtools, tool-quirk]
status: active
---

## Correction

UI/browser verification in this repo runs via the Playwright CLI wrapper (`$HOME/.claude/skills/playwright/scripts/playwright_cli.sh`, skill: `playwright`). Do NOT use chrome-devtools-mcp tooling. Run `--headed` when the user is observing; headless is fine when only telemetry/screenshots matter. Never substitute curl or programmatic-only checks for real-browser proof.

## Agent Retrieval Summary

Retrieve before any browser/UI verification step in this repo (board snapshots, agent-page interactions, dashboard-first validation, build-verifier runs, feature acceptance). The active rule: Playwright CLI for the browser session, `builder` CLI for diagnostics (logs/metrics/observability) — never substitute one for the other. Supersedes the earlier "Use MCP Chrome DevTools for dashboard testing" decision.

## User-Facing Summary

This repo verifies UI behavior by driving a real browser through the Playwright CLI, not curl and not the chrome-devtools-mcp plugin. The MCP plugin caused periodic page reloads during testing and is uninstalled here.

## Reusable Guidance

- `export PWCLI="$HOME/.claude/skills/playwright/scripts/playwright_cli.sh"` then `"$PWCLI" open <url> --headed`, `"$PWCLI" snapshot`, `"$PWCLI" click <ref>`. Re-snapshot after navigation — refs go stale on React re-renders.
- Pass `--headed` whenever the user is observing the session.
- Do not invoke any `chrome-devtools` / `chrome-devtools-mcp` tool. The plugin has been observed to cause ~10s periodic full page reloads and JS state wipes in this repo, indistinguishable from real app bugs while testing.
- Browser session proves user-visible behavior. It does not replace `builder` CLI surfaces (logs/metrics/observability) — those remain the diagnostic backbone for state.
- If a Chrome process keeps respawning despite kills, the spawn is driven by Claude Code MCP server config on the host side; killing locally won't stick.

## When To Apply

Any step that asks "does this work in the browser?" — feature acceptance, dashboard-first lifecycle validation, board/agent-page interactions, build-verifier visual checks. Apply before reaching for a browser tool, not after.

## Retrieval Queries

- browser testing tool this repo
- playwright cli wrapper
- chrome devtools mcp page reload
- ui verification headed
- dashboard validation browser
