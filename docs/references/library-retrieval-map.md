# Library Retrieval Map

All ctx7 library IDs for this codebase. Run `ctx7 docs <id> "<query>"` before
writing code that touches any surface listed here. Do not rely on training data
for any of these libraries — APIs, patterns, and config options change across
versions and training data is frequently stale.

The five critical IDs that belong in always-loaded context are repeated in
`AGENTS.md`. Everything below is the extended reference.

---

## Agent Runtime

### Claude Agent SDK (Python)

```bash
ctx7 docs /anthropics/claude-agent-sdk-python "<query>"
```

Primary runtime for `RUNTIME_SDK=claude`. Covers sessions, tool registration,
hooks, permissions, streaming, and subagent patterns. The API changes across
patch releases — always retrieve before touching
`src/autonomous_agent_builder/agents/`.

Extended coverage (821 snippets):

```bash
ctx7 docs /nothflare/claude-agent-sdk-docs "<query>"
```

Key queries:
- `"hooks PreToolUse PostToolUse"` — before editing `agents/hooks.py`
- `"permission allow deny"` — before changing permission policy
- `"subagent spawn bounded"` — before adding or modifying specialist agents
- `"session resume continuity"` — before touching `agents/runner.py`
- `"tool use structured output"` — before adding tools to `agents/tool_registry.py`

### Anthropic Python SDK

```bash
ctx7 docs /anthropics/anthropic-sdk-python "<query>"
```

Underlying model API — prompt caching, tool use, batch, streaming. Used
directly when `claude_runtime.py` or `execution_policy.py` makes raw API calls.

### OpenAI Codex CLI / SDK

```bash
ctx7 docs /openai/codex "<query>"
ctx7 docs /websites/developers_openai_codex "<query>"      # 2365 snippets
ctx7 docs /websites/developers_openai_codex_subagents "<query>"
```

`RUNTIME_SDK=codex_sdk` lane. JSON-RPC path, turn/token/duration fields,
provider-limit telemetry, native user-input format. Retrieve before touching
`services/codex_optimization.py`, `services/codex_subscription_env.py`, or
`.codex/` config.

---

## Backend

### FastAPI

```bash
ctx7 docs /fastapi/fastapi "<query>"
```

Key queries:
- `"SSE StreamingResponse"` — `api/dashboard_streams.py`
- `"lifespan startup shutdown"` — `api/app.py`
- `"Depends async dependency injection"` — route files in `api/routes/`
- `"background tasks"` — dispatch and run routes

### SQLAlchemy 2.0 (async ORM)

```bash
ctx7 docs /websites/sqlalchemy_en_20_orm "<query>"
ctx7 docs /websites/sqlalchemy_en_20 "<query>"             # core / engine docs
```

Always use 2.0-style async patterns. Legacy 1.x patterns (`Session()`,
`query()`, `relationship` lazy-load defaults) compile but behave incorrectly
under async. Key queries:
- `"AsyncSession async_sessionmaker"` — session factory setup
- `"select scalars"` — ORM queries
- `"relationship selectin lazy"` — relationship loading strategy
- `"mapped_column Mapped"` — model declarations

### Alembic

```bash
ctx7 docs /websites/alembic_sqlalchemy "<query>"
ctx7 docs /sqlalchemy/alembic "<query>"
```

Key queries:
- `"autogenerate async engine"` — `env.py` async migration setup
- `"batch alter_column"` — SQLite-safe schema changes
- `"upgrade downgrade"` — migration script structure

### Pydantic v2

```bash
ctx7 docs /pydantic/pydantic "<query>"
```

v1 → v2 is a breaking rewrite. `@validator` → `@field_validator`,
`class Config` → `model_config`, `.dict()` → `.model_dump()`. Key queries:
- `"field_validator model_validator"` — before writing validators
- `"model_config"` — before adding class-level config
- `"BaseSettings env"` — `builder_env.py`, `services/runtime_settings.py`
- `"model_dump json_schema"` — serialization and schema export

### Pydantic Settings

```bash
ctx7 docs /websites/pydantic_dev_validation "<query>"
```

### asyncpg

```bash
ctx7 docs /websites/magicstack_github_io_asyncpg_current "<query>"
```

Used for raw async Postgres connections. Key queries:
- `"create_pool pool_size"` — connection pool config
- `"fetchrow fetch"` — typed query methods
- `"transaction"` — explicit transaction blocks

### httpx (async HTTP client)

```bash
ctx7 docs /encode/httpx "<query>"
```

Used in `cli/client.py` for API calls from the CLI to the running server. Key
queries:
- `"AsyncClient timeout"` — connection/read timeout config
- `"SSE streaming iter_lines"` — consuming dashboard SSE from CLI

### Typer (CLI framework)

```bash
ctx7 docs /fastapi/typer "<query>"
```

Powers `cli/main.py` and all `cli/commands/`. Key queries:
- `"Option Argument default"` — parameter declarations
- `"callback invoke_without_command"` — subcommand groups
- `"rich_markup_mode"` — output formatting

### structlog

```bash
ctx7 docs /hynek/structlog "<query>"
ctx7 docs /websites/structlog_en_stable "<query>"
```

Key queries:
- `"configure processors"` — logger setup
- `"bind_contextvars"` — per-request context binding
- `"AsyncBoundLogger"` — async-safe logger usage

### uvicorn

```bash
ctx7 docs /websites/uvicorn_dev "<query>"
```

Key queries:
- `"workers reload"` — production vs dev config
- `"lifespan"` — startup/shutdown hooks

---

## Frontend

### React

```bash
ctx7 docs /reactjs/react.dev "<query>"
```

Key queries:
- `"useEffect cleanup"` — SSE listener teardown in dashboard
- `"Suspense lazy"` — code-split route loading
- `"useDeferredValue useTransition"` — responsive UI during agent streaming

### React Router

```bash
ctx7 docs /remix-run/react-router "<query>"
ctx7 docs /websites/reactrouter "<query>"
```

Key queries:
- `"loader action data"` — route data loading patterns
- `"useNavigate navigate"` — programmatic navigation
- `"outlet"` — nested layout routes

### Radix UI

```bash
ctx7 docs /websites/radix-ui "<query>"
ctx7 docs /radix-ui/website "<query>"
```

Headless component library. Accessibility contracts and keyboard behaviour are
defined by the component spec — do not guess. Key queries:
- `"Dialog controlled"` — modal components
- `"DropdownMenu"` — action menus
- `"Tooltip"` — hover info
- `"asChild"` — composition pattern

### Tailwind CSS

```bash
ctx7 docs /nguyenviet02/fluid-tailwindcss "<query>"
```

Key queries:
- `"arbitrary values"` — one-off sizing/color values
- `"dark mode"` — `dark:` variant usage
- `"animate"` — built-in animation utilities vs GSAP

### Vite

```bash
ctx7 docs /vitejs/vite "<query>"
ctx7 docs /websites/vite_dev "<query>"
```

Key queries:
- `"define env"` — environment variable injection
- `"proxy"` — dev server API proxy to FastAPI backend
- `"build rollupOptions"` — production bundle config

### GSAP / @gsap/react

```bash
ctx7 docs /websites/gsap "<query>"
ctx7 docs /greensock/gsap "<query>"
```

Used for dashboard animations. Key queries:
- `"useGSAP"` — React hook for GSAP timelines
- `"ScrollTrigger"` — scroll-driven animations
- `"timeline"` — sequenced animation setup

---

## Observability

### Langfuse

```bash
ctx7 docs /langfuse/langfuse-docs "<query>"
ctx7 docs /langfuse/langfuse-python "<query>"
```

Optional — installed via `[observability]` extra. Key queries:
- `"trace generation"` — tracing agent sessions
- `"score"` — quality scoring for agent runs
- `"flush"` — flushing events before process exit

---

## Quick-reference: surface → library

| Codebase surface | Retrieve first |
|---|---|
| `agents/hooks.py` | `/anthropics/claude-agent-sdk-python` hooks |
| `agents/runner.py` | `/anthropics/claude-agent-sdk-python` session |
| `agents/tool_registry.py` | `/anthropics/claude-agent-sdk-python` tool use |
| `agents/execution_policy.py` | `/anthropics/anthropic-sdk-python` models |
| `services/codex_*.py` | `/openai/codex`, `/websites/developers_openai_codex` |
| `api/app.py` | `/fastapi/fastapi` lifespan |
| `api/dashboard_streams.py` | `/fastapi/fastapi` SSE |
| `api/routes/*.py` | `/fastapi/fastapi` Depends, async |
| `db/models/*.py` | `/websites/sqlalchemy_en_20_orm` Mapped |
| `alembic/` | `/websites/alembic_sqlalchemy` |
| `builder_env.py`, `services/runtime_settings.py` | `/pydantic/pydantic` BaseSettings |
| `cli/client.py` | `/encode/httpx` AsyncClient |
| `cli/commands/*.py` | `/fastapi/typer` |
| `frontend/src/` | `/reactjs/react.dev` |
| `frontend/src/pages/` | `/remix-run/react-router` |
| `frontend/src/components/` | `/websites/radix-ui`, `/reactjs/react.dev` |
| Animation code | `/websites/gsap` useGSAP |
| Tailwind classes | `/nguyenviet02/fluid-tailwindcss` |
| Vite config | `/vitejs/vite` |
| Langfuse tracing | `/langfuse/langfuse-python` |
