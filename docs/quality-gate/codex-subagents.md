---
title: "Codex subagents quality gate"
surface: "codex-subagents"
summary: "Use when creating or changing project-scoped Codex custom agents for optimizing autonomous-agent-builder itself."
commands:
  - "workflow --docs-dir docs read REFERENCE"
  - "workflow summary codex-routing-policy"
  - "workflow summary codex-project-productivity-setup"
  - "python3 scripts/check_codex_subagents.py --repo-root ."
  - "uv run pytest tests/test_codex_subagents.py -q"
expectations:
  - "Codex custom agents live under .codex/agents and are registered from .codex/config.toml."
  - "Codex-only subagents optimize this repo and do not become Claude Agent SDK runtime agents or product-facing Builder specialists."
  - "Architecture reviewers stay read-only and return boundary map, findings, recommended owner surfaces, and next step."
  - "Code reviewers stay read-only and lead with correctness, security, regression, owner-surface, test, and severity findings."
  - "Code simplification agents can write only inside the workspace and must preserve behavior, focus on recently modified code, and report verification evidence."
  - "Each subagent recommendation is scored on evidence, actionability, scope-boundary fit, verification, and impact."
  - "Model choices use project-approved Codex model identifiers rather than provider-specific aliases."
  - "Subagents are opt-in for concrete review, simplification, or boundary reasons; deterministic gates handle routine small changes."
  - "Subagents are used for noisy evidence, review, and bounded optimization work; the main thread owns decisions and final integration."
  - "The setup reduces recurring Builder drift through deterministic checks or narrow actions instead of relying on memory-only instructions."
related_docs:
  - "docs/REFERENCE.md"
  - "docs/quality-gate/agent-quality.md"
  - "docs/workflows/agent-quality-tuning-loop.md"
---

# Codex Subagents Quality Gate

## Control Owner

This quality gate owns pass/fail expectations for repo-local Codex custom agents
used by Codex operators to optimize `autonomous-agent-builder`.

It does not own Claude Agent SDK runtime specialists, phase agents, generated-app
agents, or Builder product behavior.

## Purpose

Keep Codex project subagents useful for maintaining this repository without
blurring runtime ownership. The gate verifies that custom agents are registered,
bounded, model-valid, and explicit about being Codex operator tools rather than
Builder product agents.

## When To Load

- Before creating, renaming, or editing `.codex/agents/*.toml`.
- Before changing project `.codex/config.toml` agent registrations.
- Before recommending hooks or local actions that invoke Codex subagent review.
- During Codex productivity audits that target repo-maintenance workflow.

## Trigger Discipline

Do not trigger a Codex subagent for every small change. Use the deterministic
gate and tests first. Invoke a subagent only when there is a concrete reason:

- `architecture_reviewer`: owner-boundary ambiguity, multiple control surfaces,
  or a recurring architecture decision that needs isolated review.
- `code_reviewer`: non-trivial changed behavior, security or regression risk,
  broad diff scope, missing proof, or a final review before merge.
- `code-simplifier`: recently modified code has proven duplication, nesting,
  unclear naming, or maintenance cost that can be reduced without product
  behavior changes.

If the concrete reason is absent, do not spend tokens on a subagent.

## Pass Signals

- `python3 scripts/check_codex_subagents.py --repo-root .` returns `ok: true`.
- `builder quality-gate codex-subagents --json` exposes this contract.
- Architecture reviewers are read-only and return boundary-map-first output.
- Code reviewers are read-only and findings-first.
- Simplifier agents are behavior-preserving, recently-changed-code scoped, and
  verification-gated.
- Recommendation quality can be rated 9.5/10 or better against the rubric below.
- Runtime-boundary text makes clear these agents are not Claude Agent SDK
  product specialists.

## Recommendation Rubric

Score each subagent recommendation out of 10:

- Evidence-grounded, 2 points: cites concrete files, docs, commands, logs, tests,
  configs, or official sources.
- Actionable, 2 points: names the smallest safe next change, or clearly says no
  change is needed.
- Scope-boundary fit, 2 points: stays inside Codex repo-maintenance boundaries
  and does not claim Claude Agent SDK runtime or Builder product ownership.
- Verification, 2 points: includes proof already run, proof required, or the
  reason proof is unavailable.
- Impact, 2 points: prioritizes recommendations that prevent correctness,
  security, regression, owner-surface, maintainability, verification-cost, or
  recurring-drift failures.

Treat any recommendation below 9.5/10 as not ready for repeated use. Improve the
agent instructions, rerun the agent, and keep the main thread responsible for
accepting or rejecting the recommendation.

## Pass Criteria

- `.codex/agents/*.toml` files parse as TOML and define `name`,
  `description`, and `developer_instructions`.
- `.codex/config.toml` registers each project custom agent through a
  `config_file` entry.
- Required repo-maintenance agents are present:
  `architecture_reviewer`, `code-simplifier`, and `code_reviewer`.
- `architecture_reviewer` is read-only and requires boundary map, findings,
  recommended owner surfaces, and next step.
- `code_reviewer` is read-only and requires correctness, security, regression,
  owner-surface, test, and severity coverage.
- `code-simplifier` is workspace-write, behavior-preserving, scoped to recently
  modified code, and requires verification evidence.
- `architecture_reviewer`, `code_reviewer`, and `code-simplifier` all include
  the recommendation-quality rubric terms: evidence-grounded, actionable,
  scope-boundary, verification, and impact.
- Codex-only agents state the Claude Agent SDK boundary so future maintainers do
  not accidentally turn them into product runtime agents.
- Agent model identifiers are project-approved Codex model identifiers accepted
  by the validator. Refresh the allowlist against official Codex docs when
  adding or changing model choices.
- Subagent invocation requires a concrete trigger reason; small routine edits
  should use deterministic checks without subagent review.

## Fail Signals

- A review agent can edit files.
- A simplification agent can change behavior without explicit verification.
- A Codex project agent mentions product runtime use, phase routing, or Claude
  Agent SDK execution as its owner.
- An agent uses provider aliases such as `opus`.
- The setup adds long always-loaded instructions instead of keeping detailed
  behavior in `.codex/agents` and this gate.

## Validation

Run:

```bash
python3 scripts/check_codex_subagents.py --repo-root .
uv run pytest tests/test_codex_subagents.py -q
```
