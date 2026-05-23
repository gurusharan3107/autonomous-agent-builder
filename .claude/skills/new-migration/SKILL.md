---
name: new-migration
description: Scaffold and validate a new Alembic database migration for autonomous-agent-builder. Use this skill whenever the user says "create a migration", "new migration", "alembic revision", "add a column", "schema change", "update the database schema", or "generate migration". Trigger any time a SQLAlchemy model in src/ is added or modified.
disable-model-invocation: true
---

## Arguments

`$MIGRATION_MESSAGE` (required) — imperative description of the schema change, e.g. `"add user preferences table"` or `"add index on tasks.status"`.

If the user didn't provide a message, ask for one before proceeding.

## Steps

Run from the repo root:

```bash
cd /home/gurusharangupta/code/autonomous-agent-builder-codex-architecture-review/autonomous-agent-builder-codex-architecture-review

# 1. Generate the migration

> **Self-validate after edits.** Any change to this skill's files (SKILL.md, scripts/, references/, templates/, assets/) must be followed by `./scripts/validate.sh` from the skill directory. Hard findings → create-skill Optimize lane.
alembic revision --autogenerate -m "$MIGRATION_MESSAGE"

# 2. Capture the generated file path from stdout (looks like: Generating .../versions/xxxx_<slug>.py)
# 3. Check for drift — should report "No new upgrade operations detected"
alembic check
```

## After generation

- Print the full path of the generated migration file.
- Open and show the `upgrade()` and `downgrade()` functions so the user can review them.
- If `upgrade()` contains `drop_table` or `drop_column`, print a prominent warning:
  > ⚠ Destructive operation detected. Review carefully before applying — this cannot be auto-reversed in production.
- If `alembic check` still reports drift after generation, tell the user which model fields are unaccounted for.

## What NOT to do

Do not run `alembic upgrade head` — applying migrations is the user's explicit decision, not part of scaffolding.
