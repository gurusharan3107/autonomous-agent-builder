# Failure modes to avoid

> Loaded on demand from [roadmap-audit SKILL.md](../SKILL.md). These are real mistakes made in the unvalidated ad-hoc review that landed in INSIGHTS earlier — read once before drafting any new run.

## Failure Modes To Avoid

These are real mistakes made in the unvalidated ad-hoc review that landed in INSIGHTS earlier:

1. **Recommending a lever from the rubric without grepping `src/`.** The prior review flagged `AskUserQuestion` audit as P2 work; one grep would have shown it was already across seven sites. Always grep first.
2. **Counting a docstring or prose mention as adoption.** `services/provider_limits.py` mentions `StopFailure` in a 5-line docstring; no hook is actually registered. Read the surrounding code, not just the grep hit.
3. **Re-opening closed `[x]` items because the SDK-native version looks cleaner.** Closed work stays closed. The SDK-debt audit is for *future* prevention via pending items, not for second-guessing shipped fixes.
4. **Hardcoding the rubric date in commands.** The rubric slug includes a date (`2026-05-22-claude-agent-sdk-rubric`) that rolls forward when `knowledge-base` refreshes. Always `search` first, then `read` the returned slug.
5. **Adding an item without a `ctx7 docs` pre-requisite.** SDK signatures move between `0.2.x` minor versions. An item without the pre-requisite is a trap for the future implementer.
6. **Editing STATUS.md, NORTH-STAR.md, or any other goal/ file.** See the HARD RULE block at the top.
