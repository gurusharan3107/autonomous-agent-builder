# CLI Validation System

## Overview

Automated validation for launcher drift, repo-local CLI execution, project-memory command boundaries, and the `9+` benchmark expected from any new public CLI surface.

The validation target is not just "command runs successfully". Public CLI work should prove the benchmark owned by:
- [CLI For Agents](/Users/gurusharan/.codex/docs/references/cli-for-agents.md)
- `workflow quality-gate cli-for-agents`
- [Builder CLI quality gate](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/builder-cli.md)

## Validation Scripts

### 1. CLI Smoke Tests (`scripts/test_cli_tools.py`)

**Purpose:** Validate that the primary CLI commands actually run from this checkout.

**What it tests:**
- Workflow CLI (`--help`)
- Builder memory CLI (`list`, `search`)
- Builder script CLI (`list`)

**Usage:**
```bash
python3 scripts/test_cli_tools.py
```

### 2. CLI Launcher Validation (`scripts/validate_cli_wrappers.py`)

**Purpose:** Ensure the public workflow launcher exists and points at the expected script.

**What it checks:**
- Shell launcher exists in `~/.local/bin/`
- Launcher references the correct Python script
- Python source file is present and readable

**Usage:**
```bash
python3 scripts/validate_cli_wrappers.py
```

### 3. Memory CLI Integration Tests (`tests/integration/test_memory_cli.py`)

**Purpose:** Test that `builder memory` owns project-local memory while `workflow` remains a retrieval/control-plane surface.

**What it tests:**
- `builder memory add` creates valid files
- Files have proper structure
- `builder memory list` works in project context

**Usage:**
```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src pytest tests/integration/test_memory_cli.py -q
```

## What Issues Are Caught

### Before These Scripts

❌ Workflow launcher paths drifted out of sync with the machine
❌ Builder memory behavior changed without integration coverage
❌ No automated testing of CLI commands

### After These Scripts

✅ CLI commands tested on every verification run
✅ Missing public launchers detected automatically
✅ Integration issues caught before deployment

## 9+ Proof Set

Any new public CLI surface should be verified with a compact proof set before it is called `9+`:

1. root help is page-aligned and cheap to scan
2. startup contract works in `--json`
3. one bounded discovery path works in `--json`
4. one exact read path works in `--json`
5. one miss path returns structured retry guidance
6. one mutative path proves `--dry-run` and/or `--yes`
7. one follow or watch path proves `--ndjson` when the surface streams
8. process exit codes match the semantic taxonomy for success, invalid usage, auth/connectivity, and not-found

If any of the following are missing, the surface should be scored below `9`:
- no first-class `resolve` lane where identifiers are ambiguous
- semantic errors only exist inside JSON while the process exit code stays collapsed
- stream lanes exist without an explicit `--ndjson` contract

## Current Status

**Passing:**
- ✅ Workflow CLI smoke tests
- ✅ Builder memory CLI smoke tests
- ✅ Builder script CLI smoke tests
- ✅ Builder memory integration tests

## Maintenance

**When to run:**
- Before committing CLI changes
- After adding new CLI commands
- When updating launcher scripts
- Before calling a new public CLI surface `9+`

**When to update:**
- New public CLI tool added → update smoke tests or launcher validation
- CLI contract changes → update smoke tests and integration tests
- Launcher format changes → update validation script
- New benchmark requirement added → update the proof set and any command samples that demonstrate it
