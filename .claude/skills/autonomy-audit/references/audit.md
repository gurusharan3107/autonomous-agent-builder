# Audit lane

Run the 13 predicates against a named target. Loaded on demand when the operator chooses Audit (or types "audit autonomy of X" / "/autonomy-audit X").

## Preflight

1. **Target named.** `<target-path>` resolves to an existing directory or file. Refuse to proceed if `Path(target).exists() == False`; ask via `AskUserQuestion` for a valid path.
2. **Readable.** At least one of the target's source files (`*.py`, `*.ts`, `*.sh`, `*.md`, `*.toml`, `*.yaml`) is readable. If the entire target is unreadable, return immediately with `verdict=unknown` for every criterion.
3. **Dynamic flag deliberate.** `--dynamic` is opt-in. If passed, confirm the target is launchable (has a shebang / entrypoint / `python -m <package>` works). If not, drop the flag and proceed static-only with a one-line warning in the output's `notes` field.

## Do

```bash
# Single target, JSON output (machine-readable, the canonical form)
python3 .claude/skills/autonomy-audit/scripts/audit.py <target-path> --json

# Same target, markdown summary (human-readable view, derived from JSON)
python3 .claude/skills/autonomy-audit/scripts/audit.py <target-path>

# With dynamic probes (briefly launches target, 60s cap per probe)
python3 .claude/skills/autonomy-audit/scripts/audit.py <target-path> --dynamic

# Single criterion focus (debug / iterate during catalog development)
python3 .claude/skills/autonomy-audit/scripts/audit.py <target-path> --criterion C7

# All criteria, all targets in a parent dir
for t in <parent>/*/; do
  python3 .claude/skills/autonomy-audit/scripts/audit.py "$t" --json > "audit-$(basename $t).json"
done
```

The script reads `references/criteria.md` to know what to check. JSON shape (one element per criterion):

```json
{
  "schema_version": "1",
  "target": "<absolute-path-to-target>",
  "ran_at_utc": "2026-05-23T10:11:12Z",
  "static_only": true,
  "results": [
    {
      "id": "C1",
      "name": "Observability-first watchdog",
      "verdict": "pass | partial | fail | unknown",
      "confidence": 0.0,
      "evidence": ["...", "..."],
      "fix_pointer": "..."
    }
  ],
  "summary": {
    "pass": 0, "partial": 0, "fail": 0, "unknown": 0,
    "score_0_100": 0,
    "top_fixes": ["C7", "C12", "C13"]
  }
}
```

`score_0_100` = `(2*pass + partial) / (2 * total_criteria) * 100`, rounded. `unknown` doesn't count toward score (neutral).

`top_fixes` = the criterion IDs with `fail` or `partial` verdict, sorted by leverage (lower-numbered criteria are foundational — C1 unblocks C2 unblocks C3, etc.).

## Closeout

```bash
# 1. Self-validate (this skill's wrapper around create-skill audit)
.claude/skills/autonomy-audit/scripts/validate.sh
# Must exit 0.

# 2. (Optional) Save the JSON for downstream consumers
mkdir -p /tmp/autonomy-audit/
python3 .claude/skills/autonomy-audit/scripts/audit.py <target-path> --json \
    > /tmp/autonomy-audit/$(basename <target-path>)-$(date -u +%Y%m%dT%H%M%SZ).json
```

If the audit surfaced `fail` verdicts the operator wants addressed, those fixes are applied by the **operator** — this skill is audit-only (Hard Rule 3 in SKILL.md). The natural follow-up is:

- For skill targets: switch to `create-skill` Optimize lane.
- For app / package / repo targets: open a backlog item via `builder backlog item create --type optimization` with the audit JSON attached as evidence.

## Worked example — auditing the autoresearch skill

```bash
$ python3 .claude/skills/autonomy-audit/scripts/audit.py .claude/skills/autoresearch
# autonomy audit
target: .claude/skills/autoresearch
score: 92/100

| ID  | name                                          | verdict | confidence |
|-----|-----------------------------------------------|---------|------------|
| C1  | Observability-first watchdog                  | pass    | 0.95       |
| C2  | Preserved forensics on failure                | pass    | 0.95       |
| C3  | Pattern catalog as data structure             | pass    | 0.95       |
| C4  | unknown is a valid verdict                    | pass    | 0.90       |
| C5  | Narrow detection predicates                   | pass    | 0.85       |
| C6  | Cost-bounded cycles                           | pass    | 0.90       |
| C7  | Fixes propagate to surfaces future agents read | pass   | 0.95       |
| C8  | State, not conversation                       | pass    | 0.90       |
| C9  | Honest failure                                | pass    | 0.90       |
| C10 | Safe-to-fail at every layer                   | pass    | 0.85       |
| C11 | LLM-as-diagnoser fallback                     | fail    | 0.95       |
| C12 | Auto-apply governance                         | fail    | 0.95       |
| C13 | Meta-orchestrator with escalation             | fail    | 0.95       |

top_fixes: C11, C12, C13
```

Score 92 reflects autoresearch's strength on C1–C10 (the discovered-by-failure criteria) and its honest gap on C11–C13 (the Gap-1/2/3 items the originating session called out). This is the *intended* output shape — an audit that passes 13/13 against a skill that itself only satisfies 10/13 would be the auditor lying.
