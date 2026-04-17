# CLI Validation System

## Overview

Automated validation system to prevent cross-platform CLI issues like the workflow memory command failure on Windows.

## Validation Scripts

### 1. CLI Smoke Tests (`scripts/test_cli_tools.py`)

**Purpose:** Validates that CLI commands actually work.

**What it tests:**
- Workflow CLI (help, memory list, memory search)
- Builder memory CLI (list, search)
- Builder script CLI (list)

**Usage:**
```bash
python scripts/test_cli_tools.py
```

**Exit codes:**
- 0: All tests passed
- 1: One or more tests failed

### 2. CLI Wrapper Validation (`scripts/validate_cli_wrappers.py`)

**Purpose:** Ensures Python CLI tools have proper cross-platform wrappers.

**What it checks:**
- Bash wrapper exists in `~/.local/bin/`
- Windows batch wrapper exists in `~/.local/bin/`
- Wrappers reference correct Python scripts
- Python scripts are executable (Unix)

**Usage:**
```bash
python scripts/validate_cli_wrappers.py
```

**Exit codes:**
- 0: All wrappers validated
- 1: Missing or incorrect wrappers found

### 3. Memory CLI Integration Tests (`tests/integration/test_memory_cli.py`)

**Purpose:** Tests that builder memory and workflow memory integrate correctly.

**What it tests:**
- `builder memory add` creates valid files
- Files have proper structure
- Workflow memory can find builder-created files

**Usage:**
```bash
pytest tests/integration/test_memory_cli.py
```

## Integration with Verify Script

The validation scripts are integrated into `.claude/scripts/verify.sh`:

```bash
./claude/scripts/verify.sh
```

This runs:
1. Linting (ruff)
2. Format check (ruff)
3. **CLI smoke tests** ← NEW
4. **CLI wrapper validation** ← NEW (non-blocking)
5. Unit tests (pytest)

## What Issues Are Caught

### Before These Scripts

❌ Workflow command fails on Windows (bash script in PowerShell)
❌ Builder memory creates files in wrong location
❌ No automated testing of CLI commands
❌ Cross-platform issues discovered by users

### After These Scripts

✅ CLI commands tested on every verification run
✅ Missing wrappers detected automatically
✅ Integration issues caught before deployment
✅ Cross-platform compatibility validated

## Current Status

**Passing:**
- ✅ Workflow CLI smoke tests (6/6)
- ✅ Builder memory CLI smoke tests (2/2)
- ✅ Builder script CLI smoke tests (1/1)

**Issues Detected:**
- ⚠️  4 CLI tools missing Windows batch wrappers
- ⚠️  4 CLI tools missing bash wrappers

These are non-critical (tools still work via Python directly) but should be fixed for better UX.

## Fixing Detected Issues

### Missing Wrappers

For each tool in `~/.claude/bin/*.py`, create:

**Bash wrapper** (`~/.local/bin/toolname`):
```bash
#!/bin/bash
exec python3 "$HOME/.claude/bin/toolname.py" "$@"
```

**Windows batch wrapper** (`~/.local/bin/toolname.bat`):
```batch
@echo off
python "%USERPROFILE%\.claude\bin\toolname.py" %*
```

Make bash wrapper executable:
```bash
chmod +x ~/.local/bin/toolname
```

## Future Enhancements

1. **CI Integration**: Run validation on GitHub Actions for all platforms
2. **Auto-fix**: Script to automatically create missing wrappers
3. **Performance tests**: Add timing checks for CLI commands
4. **Memory format validation**: Validate frontmatter structure
5. **Cross-platform path tests**: Detect hardcoded Unix paths in code

## Maintenance

**When to run:**
- Before committing changes to CLI tools
- After adding new CLI commands
- When updating wrapper scripts
- As part of CI/CD pipeline

**When to update:**
- New CLI tool added → Update smoke tests
- New CLI command added → Update smoke tests
- Wrapper format changes → Update validation script
