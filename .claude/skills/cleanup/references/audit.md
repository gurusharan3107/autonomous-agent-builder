# Audit lane — detect-only sweep

Loaded on demand. NO mutations. Output: prioritized findings table the operator vetoes from.

## Preflight

Universal preflight from SKILL.md (clean git, autoresearch sweep clean). No lane-specific extras.

## Do

```bash
# 1. Run the deterministic detector
python3 .claude/skills/cleanup/scripts/audit.py --json > /tmp/cleanup-audit.json

# 2. Human-readable summary
python3 .claude/skills/cleanup/scripts/audit.py --human
```

The audit script enumerates every `.md` under `docs/` and `.claude/skills/`, computes the 7 detection signals + 4 safety blockers per file ([criteria.md](criteria.md)), emits a prioritized list. Categories:

| Category | Action recommendation |
|---|---|
| **HARD-DELETE** | 0 refs everywhere + no safety blocker hit + matches a delete signal |
| **DELETE?** | 1–2 refs only + no safety blocker; needs operator confirmation |
| **COMPACT** | Verbose-drift signal (long paras, "why this matters" footers) on otherwise load-bearing file |
| **WIRE** | Dangling refs found OR misrouted content detected |
| **KEEP** | Safety blocker hit, OR ≥3 refs with no other signal |

## Report format

Two outputs:

**Human (`--human`):** terminal table sorted by category then size:
```
category    file                                    lines  refs  signals      safety
HARD-DELETE docs/foo.md                              200     0   orphan        -
DELETE?     docs/bar.md                              150     2   historical    -
COMPACT     docs/big-ref.md                          580     5   verbose:7     blocker-B (workflows/)
WIRE        docs/qux.md                              130     3   dangling:2    -
```

**JSON (`--json`):** machine output for downstream tools:
```json
{
  "categories": {"HARD-DELETE": [...], "DELETE?": [...], "COMPACT": [...], "WIRE": [...], "KEEP": [...]},
  "summary": {"total_files": 85, "hard_delete": 3, "delete_question": 6, "compact": 12, "wire": 4, "keep": 60}
}
```

## Closeout

1. **Present categories to operator.** Lead with HARD-DELETE (highest confidence). DELETE? candidates need per-file confirmation.
2. **No file edits.** Audit lane writes nothing to docs/. The next lane (Prune/Compact/Wire) consumes the audit output.
3. **Save the JSON.** `/tmp/cleanup-audit.json` is the handoff to subsequent lanes — they read it as their work list.
4. **Recommend next lane.** Typical sequence: Audit → operator triage → Prune → Wire (dangling-ref sweep) → Compact (optional, file-by-file).

## Hard rules

- **Read-only.** Refuses to mutate any file.
- **Both signal AND safety check, always.** The 2026-05-23 false-positive on EVALUATION.md came from running the signal check without the safety check. Don't repeat it.
- **Stem + basename grep.** `library-retrieval-map.md` was missed because AGENTS.md cites it as `library-retrieval-map` (no `.md`). Audit script greps both.
