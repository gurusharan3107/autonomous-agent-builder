---
title: "Dependencies"
tags: ["dependencies", "reverse-engineering", "packages"]
doc_type: "reverse-engineering"
created: "2026-04-17T19:33:40.397710"
auto_generated: true
version: 1
---

# Dependencies

## Overview

This document lists all external dependencies used in the project.

## Python Dependencies

### Production Dependencies

- **alembic** (v1.14.0) - Database migrations
- **asyncpg** (v0.30.0)
- **claude-agent-sdk** (v0.1.0)
- **fastapi** (v0.115.0) - Web framework
- **gitpython** (v3.1.43)
- **httpx** (v0.28.0) - Async HTTP client
- **jinja2** (v3.1.4)
- **pydantic** (v2.10.0) - Data validation
- **pydantic-settings** (v2.7.0)
- **python-multipart** (v0.0.12)
- **pyyaml** (v6.0.2)
- **sqlalchemy** - ORM
- **sse-starlette** (v2.0.0)
- **structlog** (v24.4.0)
- **typer** - CLI framework
- **uvicorn** - ASGI server

### Development Dependencies

- **mypy** (v1.13) - Type checker
- **pytest** (v8.0) - Testing
- **pytest-asyncio** (v0.24.0)
- **pytest-cov** (v5.0)
- **ruff** (v0.4) - Linter

## Dependency Management

Dependencies are managed through:
- Python: `pyproject.toml` or `requirements.txt`
- Node.js: `package.json`

## Security

Regularly update dependencies to patch security vulnerabilities.
Use tools like `pip-audit` or `npm audit` to check for known issues.

