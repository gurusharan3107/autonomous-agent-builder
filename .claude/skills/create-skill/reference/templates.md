# Output skill templates

These are the exact templates to use when authoring a new skill in the Create lane.
Copy and fill placeholders — do not start from a blank file.

---

## Directory structure

```
.claude/skills/<skill-name>/
├── SKILL.md                  # Required: frontmatter + Hard Rules + 5-step workflow
├── commands/
│   └── <verb>.md             # Optional: slash command entry point(s)
├── reference/
│   ├── workflow.md           # Required: detailed step expansion
│   └── patterns.md           # Optional: domain patterns, gotchas, examples
├── evals/
│   └── evals.json            # Required: 2-3 test cases with assertions
└── scripts/
    └── validate.sh           # Optional: self-validation wrapper
```

---

## SKILL.md template

```markdown
---
name: SKILL-NAME
description: >
  Use when the user asks to VERB-PHRASE, VERB-PHRASE-2, or VERB-PHRASE-3,
  even if they don't explicitly mention DOMAIN-NOUN. Also use when the user
  says "TRIGGER-PHRASE-1", "TRIGGER-PHRASE-2", or "TRIGGER-PHRASE-3".
  Produces OUTPUT-ARTIFACT. [MODE-2 description if multi-mode.]
allowed-tools: Read, Write, Edit, Bash
---

# SKILL-NAME — ONE-LINE-SUMMARY

ONE-PARAGRAPH anchored in operator intent: what problem this solves and
what it produces. Not implementation details.

## Modes  [delete this section if single-flow]

- **Default**: DESCRIPTION. Triggered by `/SKILL-NAME:run <task>`.
- **MODE-2**: DESCRIPTION. Triggered by `/SKILL-NAME:VERB <task>`.

## Prerequisites  [delete this section if none]

One-time setup the operator must run before first use:

    SETUP-COMMAND

## Workspace Contract

- Workspace: `outputs/<task-id>/`
- Primary artifact: `PRIMARY-OUTPUT-FILE`
- All generated files stay inside workspace; never write outside it.

## Workflow

1. **PREFLIGHT** — Pick workspace. Write `scope.md` with Critical Points.
   Do not start main work until scope.md exists and every CP is listed.
2. **EXPLORE** — Read source material. Confirm approach for each CP.
   Output: content outline, stable selectors/patterns per CP.
3. **AUTHOR** — Produce the artifact one CP at a time. One action per
   step; observe output before the next.
4. **VALIDATE** — Walk scope.md CP by CP. Tick only with cited evidence
   (screenshot, log line, file content). If any CP fails: diagnose
   specific issue, fix, re-validate. Do not declare done with open CPs.
5. **CLOSEOUT** — Staleness scan (cross-refs + symbols). Pattern review
   (prune dead, annotate guards, add new from this run). Write
   `introspection.md` (staleness + friction tables). Apply every fix.
   Delete it. Deletion = done signal. Never skip — even on clean runs.

See `reference/workflow.md` for the detailed expansion of each step.

## Hard Rules

- NEVER generate content without reading provided source material first.
- NEVER declare done until every CP in `scope.md` is ticked with evidence.
- NEVER leave `introspection.md` in the workspace after closeout.
- One action per step; observe output before the next.
- DOMAIN-SPECIFIC-RULE-1 — why it matters.
- DOMAIN-SPECIFIC-RULE-2 — why it matters.

## Gotchas

- ENVIRONMENT-SPECIFIC-FACT (e.g. "The users table uses soft deletes —
  always include WHERE deleted_at IS NULL.")
- ASSUMPTION-THAT-WILL-BITE (e.g. "The /health endpoint returns 200 even
  when the database is down — use /ready for full-stack checks.")

## Reference Files

- `reference/workflow.md` — detailed PREFLIGHT → CLOSEOUT expansion
- `reference/patterns.md` — load when: CONDITION (e.g. "API returns non-200")
```

---

## reference/workflow.md template

```markdown
# Workflow — SKILL-NAME

Detailed expansion of the 5-step loop.

## 1. PREFLIGHT

1. CHECK precondition 1 (e.g. target file exists, server is running).
2. CHECK precondition 2.
3. Write `scope.md` in `outputs/<task-id>/`:

    # scope.md
    ## Critical Points
    - [ ] CP1: DESCRIPTION
    - [ ] CP2: DESCRIPTION

   Each CP must be independently verifiable from a named artifact.

## 2. EXPLORE

Goal: confirm approach for each CP before producing the main artifact.

- EXPLORATION-STEP-1 (e.g. run a read script, check an API, read a file)
- EXPLORATION-STEP-2
- Output: NAMED-OUTPUT per CP

SPA / async settle note if applicable (e.g. "wait 2 s after page load").
Batch where possible: BATCHING-GUIDANCE.

## 3. AUTHOR

Create/write the primary artifact. For each CP:

1. CP1: WHAT-TO-DO → EVIDENCE-ARTIFACT (screenshot / log line / file)
2. CP2: WHAT-TO-DO → EVIDENCE-ARTIFACT

Instrumentation rule: one EVIDENCE-ARTIFACT per CP, uniquely named.

## 4. VALIDATE

For each CP in scope.md:
1. Identify the EVIDENCE-ARTIFACT.
2. Read/inspect it. Confirm it is unambiguous.
3. Tick the CP only when evidence is concrete. Be strict.

If a CP fails:
- Diagnose the specific issue (wrong value, missing step, hidden state).
- Fix the artifact.
- Re-validate the failing CP.

## 5. CLOSEOUT

CLOSEOUT keeps the skill self-evolving: stale cross-references are removed,
dead patterns are pruned, and new failure modes are encoded on every run.
**Never skip — even on a clean run. Skipping lets the skill drift into a
historical document within weeks.**

### 5a. Staleness scan

Verify every cross-referenced file and path still exists:

    from pathlib import Path
    cross_refs = [
        # Fill with every path named in SKILL.md ## Reference Files / ## Cross-references
        "PATH-TO-FILE-1",
        "PATH-TO-FILE-2",
    ]
    for p in cross_refs:
        status = "OK " if Path(p).exists() else "STALE — remove or update cross-reference"
        print(f"{status}  {p}")

For each STALE result: update the path in SKILL.md, or remove it if the file
was deleted. Never leave a broken cross-reference.

### 5b. Symbol / assertion freshness

For each symbol, function, or key constant named in assertions or reference files:

    grep -q "SYMBOL-NAME" path/to/file \
      && echo "OK  SYMBOL-NAME" || echo "STALE — update assertion"

If STALE: update or remove the assertion. A stale assertion that silently passes
because the symbol no longer exists gives false confidence.

### 5c. Pattern review

For each "bad pattern" or guard in `reference/` files:
- **0 matches + fix is guarded in code** → keep as regression guard; add
  comment "fixed, kept as regression guard"
- **0 matches + no guard** → pattern likely gone; remove it; note in introspection.md
- **Matches found** → FAIL already reported above; no further action here

### 5d. New patterns from this run

If this run surfaced a failure mode not currently in the skill's reference files:
- New bad string → add a grep block with `Why:` explanation
- New unit regression → add a row to the relevant assertion table
- New E2E/validation observation → add a row to the observation checklist

### 5e. Write introspection.md, apply, delete

    # introspection.md — SKILL-NAME run <date>

    ## What went perfectly
    - [step name]: zero corrections needed.

    ## Staleness found and fixed
    | Item | Was | Now | File |
    |---|---|---|---|
    | cross-ref | old path | new path | SKILL.md |

    ## New patterns added
    | Pattern | Why | File |
    |---|---|---|
    | grep for X | found during run | reference/assertions.md |

    ## Patterns removed (stale)
    | Pattern | Reason for removal |
    |---|---|
    | grep for Y | fixed in source, no guard needed |

    ## Friction points
    | # | Symptom | Root cause | Fix type | Target file + section |
    |---|---|---|---|---|
    | 1 | | | UPDATE STEP / ADD GUARD | |

Fix types:
- **UPDATE STEP**: encode the correct form so future agents don't re-derive it.
- **ADD GUARD**: explicit "never do X" in Hard Rules to prevent the mistake.

Apply every row. Then:

    rm -f "outputs/<skill-name>/introspection.md"
    echo "Closeout complete — skill updated."

**The skill is only done when introspection.md is deleted.** If it still
exists, the loop is open and the skill has not yet self-improved from this run.
```

---

## commands/<verb>.md template

```markdown
---
description: WHAT-THIS-ENTRY-POINT-DOES in one sentence.
argument-hint: <natural-language task description>
---

You are operating as the SKILL-NAME agent. First read the `SKILL.md` in
the parent directory of this `commands/` folder, then complete the
following task:

$ARGUMENTS

Follow the standard SKILL-NAME workflow from `SKILL.md`.
Refer to `reference/workflow.md` for the detailed step expansion.
```

---

## evals/evals.json template

```json
{
  "skill_name": "SKILL-NAME",
  "evals": [
    {
      "id": 1,
      "prompt": "REALISTIC-USER-PROMPT-1 (specific, with context — file paths, column names, personal context)",
      "expected_output": "OBSERVABLE-SUCCESS-DESCRIPTION (not 'looks good' — name what artifact or value must exist)",
      "assertions": [
        "VERIFIABLE-STATEMENT-1 (e.g. 'output file is valid JSON')",
        "VERIFIABLE-STATEMENT-2 (e.g. 'chart has labeled axes')",
        "VERIFIABLE-STATEMENT-3"
      ]
    },
    {
      "id": 2,
      "prompt": "REALISTIC-USER-PROMPT-2",
      "expected_output": "OBSERVABLE-SUCCESS-DESCRIPTION",
      "assertions": [
        "VERIFIABLE-STATEMENT-1",
        "VERIFIABLE-STATEMENT-2"
      ]
    },
    {
      "id": 3,
      "prompt": "EDGE-CASE-OR-BOUNDARY-PROMPT (malformed input, unusual request, or ambiguous instruction)",
      "expected_output": "OBSERVABLE-SUCCESS-OR-GRACEFUL-FAILURE-DESCRIPTION",
      "assertions": [
        "VERIFIABLE-STATEMENT-1"
      ]
    }
  ]
}
```

**Tips for good test prompts:**
- Include file paths, column names, or domain values — not generic "process this data"
- Vary formality: one formal, one casual, one with abbreviation or typo
- ID 3 should test a boundary: malformed input, empty result, or unusual flag

---

## scope.md template (workspace artifact, deleted after closeout)

```markdown
# scope.md — <skill-name>

## Source material
- List every real artifact (task, file, conversation) this skill is grounded in.

## Critical Points
- [ ] CP1: Trigger — exact phrases users would type to activate this skill (3+)
- [ ] CP2: Hard Rules — failure modes; what must never happen; non-obvious guards
- [ ] CP3: Workflow — numbered steps in sequence; what each step produces
- [ ] CP4: Progressive disclosure — what content goes in reference/ vs body
- [ ] CP5: Description — ≤1024 chars, starts with imperative, names trigger phrases
- [ ] CP6: Evals — 2-3 test prompts with observable expected outputs and assertions
```
