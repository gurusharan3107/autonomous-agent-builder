---
type: pattern
phase: implementation
entity: script-library
tags: python, dynamic-loading, imports, plugin-system
status: active
date: 2026-04-16
---

# Dynamic Script Loading with Package-Relative Imports

## Context

When implementing a plugin/script system in Python where scripts need to import from a base module using relative imports (e.g., `from .base import Script`).

## Problem

Using simple module names in `importlib.spec_from_file_location()` breaks relative imports because the dynamically loaded module isn't part of the package hierarchy.

## Approach

Use fully-qualified module names that match the package structure:

```python
# Instead of:
module_name = script_name  # e.g., "update_dashboard"

# Use:
module_name = f'autonomous_agent_builder.embedded.scripts.{script_name}'

# Then load normally:
spec = importlib.util.spec_from_file_location(module_name, script_path)
module = importlib.util.module_from_spec(spec)
sys.modules[module_name] = module  # Register with full path
spec.loader.exec_module(module)
```

## Benefits

- Scripts can use relative imports (`from .base import Script`)
- Module is properly integrated into package hierarchy
- No need to manipulate `sys.path`
- Works consistently across different execution contexts

## When Applied

This pattern was critical for the script library implementation in Task 11-14, where scripts in `src/autonomous_agent_builder/embedded/scripts/` needed to import from `.base` module.
