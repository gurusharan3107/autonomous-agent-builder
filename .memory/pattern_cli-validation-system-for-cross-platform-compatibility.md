---
title: CLI validation system for cross-platform compatibility
type: pattern
date: 2026-04-17
phase: implementation
entity: cli-validation
tags: [cli, validation, cross-platform, legacy]
status: invalidated
flag_reason: "Legacy memory referenced verify.sh, which is absent; current CLI validation is owned by docs/cli-validation.md and command-execution-friction-prevention-via-steering-files."
---

Automated validation system prevents cross-platform CLI issues. Three-tier approach: 1) CLI smoke tests validate commands work (test_cli_tools.py), 2) Wrapper validation ensures bash and batch wrappers exist (validate_cli_wrappers.py), 3) Integration tests verify builder memory and workflow memory interop. Integrated into verify.sh. Catches issues like bash scripts failing in PowerShell, missing Windows wrappers, and files created in wrong locations. Run python scripts/test_cli_tools.py before commits.
