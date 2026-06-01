# Description testing — trigger eval loop

A skill only helps if it activates. This guide tests and improves the
`description` field so it fires on the right prompts and not the wrong ones.

---

## How triggering works

Agents load only `name` and `description` at startup. When a user's task
matches the description, the agent reads the full `SKILL.md`. If the description
is too narrow the skill never fires; too broad and it fires for unrelated tasks.

One nuance: agents typically only consult skills for tasks beyond what they can
handle with basic tools. A one-liner request may not trigger even with a
perfect description — complex, multi-step, or domain-specific tasks are where
description precision matters most.

---

## Step 1 — Write eval queries

Aim for **~20 queries (8-10 should-trigger, 8-10 should-not)** — enough to split
train/validation meaningfully. 10 (5+5) is the absolute floor for a quick check.
Create `outputs/<skill-name>/eval_queries.json` (the 5+5 below is the minimum
shape — add more, varying phrasing/explicitness/detail/complexity):

```json
[
  { "query": "SHOULD-TRIGGER-1 (formal, names domain directly)", "should_trigger": true },
  { "query": "SHOULD-TRIGGER-2 (casual, no domain keyword — tests proxy phrasing)", "should_trigger": true },
  { "query": "SHOULD-TRIGGER-3 (with file paths and personal context)", "should_trigger": true },
  { "query": "SHOULD-TRIGGER-4 (abbreviated or typo variant)", "should_trigger": true },
  { "query": "SHOULD-TRIGGER-5 (multi-step workflow request)", "should_trigger": true },
  { "query": "SHOULD-NOT-TRIGGER-1 (near-miss — shares a keyword but different task)", "should_trigger": false },
  { "query": "SHOULD-NOT-TRIGGER-2 (near-miss — adjacent domain)", "should_trigger": false },
  { "query": "SHOULD-NOT-TRIGGER-3 (near-miss — same noun, different verb)", "should_trigger": false },
  { "query": "SHOULD-NOT-TRIGGER-4 (obvious irrelevant)", "should_trigger": false },
  { "query": "SHOULD-NOT-TRIGGER-5 (involves skill output but is a different task)", "should_trigger": false }
]
```

**Near-miss queries are the most valuable.** Weak negatives ("write a Fibonacci
function") test nothing. Strong negatives share keywords but need something
different — if your skill is `csv-analyzer`, strong negatives include
"update the formulas in my Excel budget" and "write a Python script to
upload CSV rows to Postgres".

---

## Step 2 — Train/validation split

Split `eval_queries.json` into two files before optimizing:

```bash
python3 - <<'PY'
import json, random
queries = json.load(open("outputs/SKILL-NAME/eval_queries.json"))
random.shuffle(queries)
split = int(len(queries) * 0.6)
json.dump(queries[:split], open("outputs/SKILL-NAME/train_queries.json", "w"), indent=2)
json.dump(queries[split:], open("outputs/SKILL-NAME/val_queries.json", "w"), indent=2)
print(f"Train: {split}, Val: {len(queries)-split}")
PY
```

Only use the **train set** to guide description changes. The **validation set**
stays untouched until you select your best iteration.

---

## Step 3 — Test trigger rate

For each query, activate the skill and check whether it fires. Run each
query 3 times (model output is nondeterministic):

```bash
# Manual approach: activate the skill with each query and observe whether
# SKILL.md loads. Skill triggered = agent mentions or follows skill instructions.
# Record: query | should_trigger | triggered (Y/N) | notes

# Programmatic approach (Claude Code CLI):
for query in $(jq -r '.[].query' outputs/SKILL-NAME/train_queries.json); do
  echo "--- Testing: $query"
  claude -p "$query" --output-format json 2>/dev/null \
    | jq -e 'any(.messages[].content[]; .type == "tool_use" and .name == "Skill" and .input.skill == "SKILL-NAME")' \
    && echo "TRIGGERED" || echo "NOT TRIGGERED"
done
```

A query passes if:
- `should_trigger: true` → skill invoked (trigger rate ≥ 0.5 across 3 runs)
- `should_trigger: false` → skill not invoked (trigger rate < 0.5)

---

## Step 4 — Optimization loop

Repeat until train set pass rate ≥ 80% or 5 iterations:

1. **Identify failures** from train set only:
   - Should-trigger misses → description too narrow → broaden scope or add proxy phrases
   - Should-not-trigger false fires → description too broad → add boundary clause

2. **Revise the description**:
   - Don't add specific keywords from failed queries — that's overfitting
   - Find the general category the failed queries represent and address that
   - Check you're still ≤1024 chars after edits
   - Try a structurally different framing if stuck after 2–3 iterations

3. **Re-evaluate** train set. Track pass rate per iteration.

4. **Select best iteration** by **validation** pass rate — not train pass rate.
   The best description may not be the last one produced.

---

## Step 5 — Apply and verify

Update `description:` in `SKILL.md`.

```bash
# Final sanity check: 5 fresh prompts (never seen during optimization)
# Should-trigger: 3 prompts  |  Should-not-trigger: 2 prompts
# If all 5 pass → description generalizes. If not → one more iteration.
```

**Before / After example:**

```yaml
# Before — too narrow, no proxy phrases
description: Process CSV files.

# After — intent-focused, proxy phrases, boundary clause
description: >
  Analyze CSV and tabular data files — compute statistics, add derived
  columns, generate charts, and clean messy data. Use when the user has
  a CSV, TSV, or Excel file and wants to explore, transform, or visualize
  it, even if they don't say "CSV" or "analysis." Not for database ETL
  or uploading data to external services.
```
