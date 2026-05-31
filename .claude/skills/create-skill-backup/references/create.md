# Create lane — scaffold a new skill

Loaded on demand when the operator picks the Create lane (or types "create / scaffold / add a skill for X").

## Preflight

1. **Name not taken** — `ls .claude/skills/<name>` returns nothing.
2. **Name is kebab-case** — passes `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`. See [spec.md § Name validation](spec.md).
3. **Real use case named** — per agentskills.io best practices, prefer extracting from a hands-on task or synthesizing from existing project artifacts over generic theory. If the operator can't name a concrete trigger phrase + concrete output, ask via `AskUserQuestion` before scaffolding.

## Do

```bash
SKILL_NAME="<kebab-case-name>"
mkdir -p ".claude/skills/${SKILL_NAME}/scripts" \
         ".claude/skills/${SKILL_NAME}/references"
cp .claude/skills/create-skill/templates/SKILL.md.template \
   ".claude/skills/${SKILL_NAME}/SKILL.md"

# Every skill must carry its own self-validation wrapper. Single source of
# truth — do not customize per-skill; the wrapper resolves the canonical
# audit.py via repo-root lookup.
cp .claude/skills/create-skill/templates/validate.sh \
   ".claude/skills/${SKILL_NAME}/scripts/validate.sh"
chmod +x ".claude/skills/${SKILL_NAME}/scripts/validate.sh"
```

Then `Edit` the placeholders. Required edits:

| Field | What to write |
|---|---|
| `name:` | kebab-case, must equal the directory name |
| `description:` | See [description.md](description.md) for the project style guide. Lead with what the skill does, list trigger phrases explicitly, include "Use when …" phrasing, name what it touches and what it returns. |
| `allowed-tools:` | Minimum needed; remove the line entirely if the skill is pure prose guidance. |
| Body sections | Replace stubs with real procedure. |

## Closeout

```bash
# 1. Self-validate via the skill's own wrapper — must exit 0.
".claude/skills/${SKILL_NAME}/scripts/validate.sh"

# 2. Cross-runtime portability check — optional, only if the skill should work outside this repo
#    (Codex / Gemini / Cursor / etc.). Promotes spec-soft warnings to hard.
".claude/skills/${SKILL_NAME}/scripts/validate.sh" --strict
```

Every skill carries `scripts/validate.sh` — a thin wrapper around the canonical `create-skill/scripts/audit.py`. The wrapper is identical in every skill (do not customize); it just makes self-validation one command away no matter which skill you're in.

If the skill auto-fires on operator phrases (`/start`, `/save-session`, `/goal-audit` precedent), add a row to the Skill Triggers table in `AGENTS.md`. **Do not** edit `AGENTS.md` before running `workflow quality-gate agents-md` per the project's AGENTS.md required-triggers contract.

## Author principles (specific to Create lane)

- **Start from real expertise** (agentskills.io best practice). The most effective skills are extracted from a real task you've already done with an agent — complete it, correct it, then crystallize the pattern. Generic-best-practice skills age poorly.
- **One purpose per skill.** Multi-lane skills exist (this one, autoresearch) but the lanes must share a single operator-vocabulary noun. If you're stretching to find a shared noun, it's two skills.
- **Body is a router, not a content dump.** Lane Preflight/Do/Closeout content goes in `references/<lane>.md`; the body links to it. This skill demonstrates the pattern — see `SKILL.md` (router) + this file (lane detail).
- **Scripts must be deterministic.** Anything in `scripts/` runs without model judgment. If the operation needs judgment, that's body or reference content, not a script.
