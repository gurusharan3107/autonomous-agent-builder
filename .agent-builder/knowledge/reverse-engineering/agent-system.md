---
title: "Agent System"
tags: ["agents", "tools", "hooks", "security", "reverse-engineering"]
doc_type: "reverse-engineering"
created: "2026-04-17T19:33:56.761128"
auto_generated: true
version: 1
---

# Agent System

## Overview

This document describes the agent system, including agent definitions,
available tools, and security hooks.

## Agent Definitions

The system uses an agent-as-artifact pattern where agents are versioned and immutable at execution.

### chat

General-purpose conversational agent for project assistance

**Model**: sonnet

**Max Turns**: 15

**Max Budget**: $2.0

**Tools**: Read, Glob, Grep, mcp__builder__kb_search, mcp__builder__memory_search, mcp__builder__task_list, mcp__builder__task_show

### planner

Break features into implementation tasks with dependencies

**Model**: opus

**Max Turns**: 20

**Max Budget**: $3.0

**Tools**: Read, Glob, Grep, mcp__builder__kb_search, mcp__builder__memory_search

### designer

Create architecture decisions and API contracts

**Model**: opus

**Max Turns**: 20

**Max Budget**: $3.0

**Tools**: Read, Glob, Grep, mcp__builder__kb_add, mcp__builder__kb_search, mcp__builder__memory_search

### code-gen

Implement features in isolated workspace

**Model**: sonnet

**Max Turns**: 30

**Max Budget**: $5.0

**Tools**: Read, Edit, Write, Bash, Glob, Grep, mcp__workspace__run_tests, mcp__workspace__run_linter, mcp__builder__kb_search, mcp__builder__memory_search (and 1 more)

### pr-creator

Create pull requests with quality evidence

**Model**: sonnet

**Max Turns**: 15

**Max Budget**: $2.0

**Tools**: Read, Bash, Glob, Grep

### build-verifier

Verify post-merge build and integration tests pass

**Model**: sonnet

**Max Turns**: 10

**Max Budget**: $1.5

**Tools**: Read, Bash, Glob, Grep

## Available Tools

Tools are organized into categories:

### Other

- **validate_tool_call**: Validate a tool call shape before execution. Fail fast.

### Read-Only

- **get_tool_prompt_context**: Generate tool descriptions for injection into agent prompts.
- **list_tools**: Return list of available tool names.

## Security Hooks

The system uses SDK hooks for security and audit:

### Enforce Workspace Boundary

**Type**: Unknown

PreToolUse hook: block file operations outside workspace.

SDK signature: (input: PreToolUseHookInput, tool_use_id, context: HookContext)
Returns empty dict to allow, or {"decision": "block", "reason": ...} to deny.

**Purpose**: PreToolUse hook: block file operations outside workspace.

### Validate Bash Argv

**Type**: Unknown

PreToolUse hook: validate Bash tool uses argv-safe commands.

SDK signature: (input: PreToolUseHookInput, tool_use_id, context: HookContext)

Non-negotiable security constraint from architecture council:
- No shell metacharacters (|, ;, &, `, $)
- No command chaining (&&, ||)
- No redirection (>>, <<)
- No eval/exec/source

**Purpose**: PreToolUse hook: validate Bash tool uses argv-safe commands.

### Audit Log Tool Use

**Type**: Unknown

PostToolUse hook: log all tool calls for audit trail.

SDK signature: (input: PostToolUseHookInput, tool_use_id, context: HookContext)

Every tool invocation is recorded with input/output for replay capability.
This replaces the need for a SessionRegistry — structured logs provide
full audit trail.

**Purpose**: PostToolUse hook: log all tool calls for audit trail.

## Agent Execution Flow

1. **Agent Selection**: Orchestrator selects agent based on task phase
2. **Tool Registry**: Tools are registered and validated
3. **Hook Registration**: Security hooks are attached
4. **Execution**: Agent runs with SDK query() method
5. **Audit**: All tool calls are logged via PostToolUse hook

## Tool Access Control

- **Read-only tools**: Glob, Grep, Read
- **Write tools**: Write, Edit (workspace-restricted)
- **Execution tools**: Bash (argv-validated)
- **MCP tools**: Custom tools via Model Context Protocol

## Security Constraints

- Workspace boundary enforcement (PreToolUse)
- Bash command validation (no shell metacharacters)
- Tool call audit logging (PostToolUse)
- Permission caching with TTL

