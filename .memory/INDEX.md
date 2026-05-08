# Memory Index

Generated: 2026-04-29 | Memories: 47 (43 active, 3 graduated, 1 invalidated)

Source of truth: `.memory/routing.json`, refreshed with `builder memory reindex`.
Use `builder memory list --limit 100 --json` for the full routed inventory and
`builder memory show <slug>` for a specific memory.

## Counts

- Status: active(43) | graduated(3) | invalidated(1)
- Type: pattern(23) | decision(15) | correction(9)
- Phase: implementation(26) | testing(12) | design(5) | setup(2) | integration(1) | planning(1)

## Graduated

These memories are preserved as precedent but their durable guidance now lives in
workflow docs.

- `test-continuation-with-user-shaped-prompts` -> `docs/workflows/forward-engineering-autonomous-lifecycle-validation.md`
- `testing-closeout-should-save-anecdotes-and-typed-backlog-fin` -> `docs/workflows/forward-engineering-autonomous-lifecycle-validation.md`
- `feature-chat-fixes-must-be-sdk-grounded-not-keyword-patched` -> `docs/workflows/agent-quality-tuning-loop.md`

## Invalidated

- `cli-validation-system-for-cross-platform-compatibility`: legacy memory referenced
  `verify.sh`, which is absent. Current CLI validation is owned by
  `docs/cli-validation.md` and
  `command-execution-friction-prevention-via-steering-files`.

## Active Inventory

The active set is intentionally routed through the builder CLI so agents do not
depend on a stale hand-maintained table.

- List all active memories: `builder memory list --limit 100 --json`
- Search by concern: `builder memory search "<query>" --brief`
- Load one memory: `builder memory show <slug>`
- Rebuild routing after memory file changes: `builder memory reindex --json`
- Validate memory health: `builder memory lint --json`
