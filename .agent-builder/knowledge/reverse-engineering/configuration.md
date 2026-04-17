---
title: "Configuration"
tags: ["configuration", "settings", "environment", "reverse-engineering"]
doc_type: "reverse-engineering"
created: "2026-04-17T19:33:54.191663"
auto_generated: true
version: 1
---

# Configuration

## Overview

This document describes all configuration options, environment variables,
and settings for the system.

## Configuration Classes

### DatabaseSettings

Database connection settings. Supports PostgreSQL (prod) and SQLite (local dev).

**Settings**:

- **host** (str) - Default: `localhost`
- **port** (int) - Default: `5432`
- **name** (str) - Default: `agent_builder`
- **user** (str) - Default: `agent_builder`
- **password** (str) - Default: `agent_builder`
- **driver** (str) - Default: `sqlite`
- **url_override** (Any) - Default: `None`

### AgentSettings

Agent runtime settings.

**Settings**:

- **max_turns** (int) - Default: `30`
- **max_budget_usd** (float) - Default: `5.0`
- **planning_model** (str) - Default: `opus`
- **design_model** (str) - Default: `opus`
- **implementation_model** (str) - Default: `sonnet`
- **pr_model** (str) - Default: `sonnet`
- **permission_mode** (str) - Default: `dontAsk`

### GateSettings

Quality gate settings.

**Settings**:

- **max_retries** (int) - Default: `2`
- **retry_backoff** (list) - Default: `Field(...)`
- **code_quality_timeout** (int) - Default: `30`
- **testing_timeout** (int) - Default: `120`
- **security_timeout** (int) - Default: `60`
- **dependency_timeout** (int) - Default: `45`

### HarnessSettings

Harnessability scoring settings.

**Settings**:

- **reject_threshold** (int) - Default: `3`
- **review_threshold** (int) - Default: `5`

### Settings

Root settings — aggregates all sub-settings.

**Settings**:

- **app_name** (str) - Default: `Autonomous Agent Builder`
- **debug** (bool) - Default: `False`
- **host** (str) - Default: `0.0.0.0`
- **port** (int) - Default: `8000`
- **workspace_root** (str) - Default: `/tmp/aab-workspaces`
- **db** (DatabaseSettings) - Default: `Field(...)`
- **agent** (AgentSettings) - Default: `Field(...)`
- **gate** (GateSettings) - Default: `Field(...)`
- **harness** (HarnessSettings) - Default: `Field(...)`

## Configuration Files

### pyproject.toml

Project metadata and dependencies.

### .env

Environment-specific configuration (not committed to git).

### config.yaml

Application configuration (if applicable).

## Configuration Precedence

Configuration is loaded in this order (later overrides earlier):

1. Default values in code
2. Configuration files
3. Environment variables
4. Command-line arguments

## Security

- Never commit `.env` files to version control
- Use environment variables for secrets
- Rotate credentials regularly
- Use different configs for dev/staging/prod

