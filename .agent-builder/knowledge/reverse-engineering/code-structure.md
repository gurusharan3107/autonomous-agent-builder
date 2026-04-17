---
title: "Code Structure"
tags: ["code-structure", "reverse-engineering", "organization"]
doc_type: "reverse-engineering"
created: "2026-04-17T19:33:44.055593"
auto_generated: true
version: 1
---

# Code Structure

## Code Organization

This document describes how the code is organized, including module structure,
key files, and coding patterns.

## Module Structure

### `src\autonomous_agent_builder`

Autonomous Agent Builder — production-grade SDLC automation using Claude Agent SDK.

**Key Files**:
- `config.py` - Configuration
- `main.py` - Source file
- `__main__.py` - Source file

### `src\autonomous_agent_builder\agents`

Python module

**Key Files**:
- `definitions.py` - Source file
- `hooks.py` - Source file
- `runner.py` - Source file
- `tool_registry.py` - Source file

### `src\autonomous_agent_builder\api`

Python module

**Key Files**:
- `app.py` - Source file
- `schemas.py` - API request/response schemas

### `src\autonomous_agent_builder\cli`

builder CLI — agent-first interface to the autonomous SDLC system.

**Key Files**:
- `client.py` - Source file
- `main.py` - Source file
- `output.py` - Source file
- `port_manager.py` - Source file
- `project_discovery.py` - Source file

### `src\autonomous_agent_builder\dashboard`

Python module

**Key Files**:
- `routes.py` - API route handlers

### `src\autonomous_agent_builder\db`

Python module

**Key Files**:
- `models.py` - Data models and database schema
- `session.py` - Source file

### `src\autonomous_agent_builder\embedded`

Embedded resources for project-level agent builder. 

### `src\autonomous_agent_builder\harness`

Python module

**Key Files**:
- `harnessability.py` - Source file

### `src\autonomous_agent_builder\integrations`

Python module

### `src\autonomous_agent_builder\knowledge`

Knowledge extraction and management.

**Key Files**:
- `agent_extractor.py` - Source file
- `agent_quality_gate.py` - Source file
- `document_spec.py` - Source file
- `extractor.py` - Source file
- `quality_gate.py` - Source file

### `src\autonomous_agent_builder\observability`

Python module

**Key Files**:
- `logging.py` - Source file

### `src\autonomous_agent_builder\orchestrator`

Python module

**Key Files**:
- `gate_feedback.py` - Source file
- `orchestrator.py` - Source file

### `src\autonomous_agent_builder\quality_gates`

Python module

**Key Files**:
- `base.py` - Source file
- `code_quality.py` - Source file
- `security.py` - Source file
- `testing.py` - Source file

### `src\autonomous_agent_builder\security`

Security module — prompt injection detection, egress monitoring, permission store. 

**Key Files**:
- `egress_monitor.py` - Source file
- `permission_store.py` - Source file
- `prompt_inspector.py` - Source file

### `src\autonomous_agent_builder\services`

Python module

## Key Files

- `src\autonomous_agent_builder\main.py` - Application entry point
- `src\autonomous_agent_builder\cli\main.py` - Application entry point
- `src\autonomous_agent_builder\api\app.py` - Application factory
- `.agent-builder\server\app.py` - Application factory
- `src\autonomous_agent_builder\config.py` - Configuration management
- `src\autonomous_agent_builder\db\models.py` - Data models
- `src\autonomous_agent_builder\api\schemas.py` - API schemas
- `src\autonomous_agent_builder\dashboard\routes.py` - API routes
- `pyproject.toml` - Python project configuration

## Design Patterns

Common design patterns used in this codebase:
- **Dependency Injection**: Used for loose coupling
- **Factory Pattern**: For object creation
- **Repository Pattern**: For data access abstraction
- **Strategy Pattern**: For algorithm selection

## Code Conventions

- Follow PEP 8 style guide (Python)
- Use type hints for better code clarity
- Write docstrings for public APIs
- Keep functions focused and small

