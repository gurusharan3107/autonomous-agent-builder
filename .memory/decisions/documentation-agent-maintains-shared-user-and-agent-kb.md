---
title: Documentation agent maintains shared user and agent KB
type: decision
date: 2026-04-22
phase: implementation
entity: documentation-agent
tags: [kb, docs, agent, system-docs]
status: active
---

The embedded documentation-agent owns repo-local knowledge maintenance for both human users and future agents. It should refresh broader app context through the canonical builder knowledge extract lane for system-docs and keep maintained feature docs agent-friendly with purpose, key files, change guidance, verification, and reminders. It must stay within .agent-builder/knowledge and not write memory or docs/.
