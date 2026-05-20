# Agent Sprint Cycle Validation Progress

Last updated: 2026-05-16

## Checklist

- [x] Start validation from the live managed `todo-app` Agent page using
  Computer Use, not headless browser automation.
- [x] Validate that a persisted pending delivery approval is visible and
  actionable after refresh.
- [x] Fix persisted approval recovery so approving delivery scope creates the
  sprint plan without requiring the original live waiter.
- [x] Verify approval-to-plan in the visible Agent page for session
  `b48fc8cf-59b7-4dea-97e3-59b717eea602`.
- [x] Capture token evidence for the next live continuation run.
- [x] Fix the `start` continuation bug so ready sprint work dispatches through
  Builder task state instead of generic model-backed chat.
- [ ] Re-run a clean feature cycle from a fresh app/session to prove task
  dispatch, implementation, verification, and Board completion all stay
  synchronized end to end.
- [ ] Add a hardening issue for generated-app feature runs mutating owner
  surfaces such as `AGENTS.md` or `CLAUDE.md` when the approved task scope only
  calls for app/test files.

## Live Findings

- The visible UI now recovers hidden pending decisions from persisted history.
- `approve` created sprint plan `sprint-plan-6a41b3ba1754` with three work
  steps for `Text search for todos`.
- The first post-plan `start` run consumed `87,121` raw tokens but `85,888`
  were cached; the non-cached plus output surface was `1,233`.
- The misrouted `start` run implemented the feature directly, but left Builder
  task state queued/planning. Future `start` prompts with dispatchable sprint
  tasks now take the task-dispatch lane.
