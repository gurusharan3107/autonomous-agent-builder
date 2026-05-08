# Main Commit Reference

Canonical reference for the maintained-doc freshness baseline used by this repo
and by reverse-engineering runs against external repos.

For where documentation refresh belongs in the autonomous delivery lifecycle,
see
[autonomous-delivery-documentation-refresh.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/autonomous-delivery-documentation-refresh.md).

Use this doc as the owner surface when changing:
- what `documented_against_commit` means
- which git ref is canonical for maintained `feature` and `testing` docs
- how documentation automation resolves the baseline commit
- when a documentation run may advance the canonical freshness baseline

## Purpose

Maintained documentation needs one stable commit reference so freshness checks
stay deterministic and token-efficient.

For this repo, that canonical reference is the local git ref `main`.

For external repos onboarded through reverse engineering, the product should
resolve the repo's canonical branch dynamically: prefer `main` when it exists,
otherwise use the remote default branch or the current checked-out branch.

The system should decide freshness by comparing maintained-doc metadata against
the current `main` baseline, not by asking an agent to rediscover the whole
repo on every run.

## Canonical Contract

For maintained `feature` and `testing` docs:

- `documented_against_ref` must match the repo's canonical baseline branch
- `documented_against_commit` must record the exact commit SHA from that
  baseline branch
- `owned_paths` must contain the repo-relative paths used to detect whether the
  doc became stale

The current canonical baseline is resolved with the same contract used by the
freshness checker. In this repo that is still:

```bash
git rev-parse main
```

In code, the owner surface is
[`maintained_freshness.py`](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/knowledge/maintained_freshness.py),
where `CANONICAL_DOC_REF = "main"` remains the preferred baseline and
`resolve_canonical_doc_ref(...)` handles repos that do not use `main`.

## When The Baseline May Advance

Only canonical-baseline documentation refreshes may advance
`documented_against_commit`.

That means:

- documentation runs evaluating the checked-out canonical baseline may stamp a
  new `documented_against_commit`
- non-canonical runs may inspect and report likely stale docs, but they must
  stay advisory-only and must not advance the canonical baseline

This keeps feature-branch or experimental runs from rewriting the repo's
authoritative documentation freshness state.

## Why One Canonical Branch Owns The Baseline

This repo uses `main` as that branch. External reverse-engineering repos may
use another default branch, but each repo still needs exactly one canonical
baseline for maintained docs.

Using a single canonical ref gives the system:

- deterministic freshness checks
- bounded candidate selection through `owned_paths`
- low-token doc maintenance because the agent wakes only for stale docs
- one shared baseline across local validation, documentation-agent work, and CI

Do not create per-branch canonical baselines for maintained docs unless the
repo's delivery model changes and the owning code plus quality gates are
updated together.

## Consumer Rules

### Documentation agent

The documentation agent should:

- resolve the current canonical baseline HEAD before deciding refresh work
- use stale docs plus `owned_paths` to keep retrieval bounded
- stamp `documented_against_commit`, `documented_against_ref=<canonical_ref>`,
  and `owned_paths` after a canonical refresh

### Quality gate

`builder knowledge validate --json` should remain the authoritative freshness
gate. It should compare maintained-doc metadata against the current canonical
baseline and report exact stale reasons.

### CI or automation

External automation such as a `push`-to-`main` workflow should use this same
baseline. Best practice is:

1. resolve the current canonical checkout
2. run `builder knowledge validate --json`
3. invoke the documentation agent only for the stale docs the validator reports
4. re-run validation before reporting success

The concrete repo-owned implementation lives in:

- [.github/workflows/documentation-freshness.yml](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/.github/workflows/documentation-freshness.yml)
- `builder agent documentation-refresh --validation <file> --json`
- [documentation_freshness_ci.py](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/knowledge/documentation_freshness_ci.py)
- [documentation_bridge.py](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/agents/documentation_bridge.py)

That workflow intentionally fails fast when deterministic validation reports
non-freshness issues. The Claude lane should wake only for bounded maintained
doc freshness gaps, not for broader knowledge-base breakage. The workflow
should use the repo-owned documentation-agent bridge rather than invoking a
freeform Claude action prompt directly.

## Anti-Patterns

- treating a documentation write as fresh without stamping the canonical fields
- advancing `documented_against_commit` from a non-canonical branch run
- using a broad repo scan when `owned_paths` already localize the stale surface
- inventing a second owner doc for the `main` baseline contract

## Related Docs

- [documentation-agent.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/documentation-agent.md)
- [knowledge-base.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/knowledge-base.md)
- [knowledge-document-format.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/knowledge-document-format.md)
- [maintained_freshness.py](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/src/autonomous_agent_builder/knowledge/maintained_freshness.py)
