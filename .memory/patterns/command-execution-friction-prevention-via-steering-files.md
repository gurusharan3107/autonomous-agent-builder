---
title: Command execution friction prevention via steering files
type: pattern
date: 2026-04-17
phase: implementation
entity: steering
tags: [friction, commands, windows, automation]
status: active
---

## Approach

When encountering recurring friction (interactive commands, platform issues, tool misuse), encode the solution in steering files rather than relying on memory or repeated corrections.

**Pattern:**
1. Identify friction: Command hangs, errors, or requires repeated fixes
2. Create/update steering file: `.kiro/steering/<topic>.md`
3. Document with examples: ❌ WRONG vs ✅ CORRECT patterns
4. Set inclusion: `auto` for always-loaded, `manual` for context-specific
5. Add to AGENTS.md: Reference in triggers or quick commands

**Structure:**
- Critical Rules: Clear directives with anti-patterns
- Common Friction Patterns: Problem → Solution format
- Quick Reference: Cheat sheet of safe commands
- Decision Log: Why this exists, when to update

## When To Reuse

**Use this pattern when:**
- Same error occurs across multiple sessions
- Platform-specific issues need documentation (Windows vs Unix)
- Interactive commands need non-interactive alternatives
- Tool misuse patterns emerge (shell commands vs Kiro tools)
- Environment quirks require workarounds (PATH issues, CLI wrappers)

**Examples:**
- Interactive curl requests → Document complete request patterns
- Workflow CLI hanging on Windows → Document Python direct invocation
- npm not in PATH → Document full path usage
- Unix commands on Windows → Document PowerShell or Kiro tool alternatives

## Evidence

**Created:** `.kiro/steering/command-execution-patterns.md` (2026-04-17)
- Documents 8 critical rules for command execution
- Covers interactive commands, Windows compatibility, API testing, workflow CLI
- Includes quick reference of safe vs unsafe commands
- Prevents recurring friction with curl, npm, workflow CLI, dev servers

**Updated:** `AGENTS.md` (2026-04-17)
- Added AFTER trigger: "AFTER friction encountered → Encode solution in steering"
- Added "Friction Prevention Doctrine" section
- Defines what qualifies as friction
- Provides steering file structure template
- Includes create vs update guidelines

**Impact:**
- Reduces repeated mistakes across sessions
- Provides immediate reference for common issues
- Scales better than memory (auto-loaded vs query-based)
- Creates living documentation of environment constraints


