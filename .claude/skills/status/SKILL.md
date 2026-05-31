---
name: status
description: >
  Use when the operator wants to open or refresh the goal overview page —
  "/status open", "/status update", "open the goal overview", "show the goal
  overview", "update the status page", "refresh goal-overview", "sync the goal
  overview", "regenerate the goal overview". Two lanes: open (launch
  docs/goal/goal-overview.html in a browser) and update (deterministically
  regenerate its live numbers from the canonical docs/goal/ROADMAP.md +
  STATUS.md, then report what changed). NOT for editing ROADMAP/STATUS content
  (those are the source of truth) and NOT for project quality audits (/audit).
allowed-tools: Bash
---

# status — open / refresh the goal overview

`docs/goal/goal-overview.html` is a hand-authored operator page that **mirrors**
the canonical `docs/goal/*.md`. It has no runtime data-loading, so its numbers
drift. This skill keeps it honest and opens it.

- **`/status open`** → launch the page in a browser.
- **`/status update`** → run the deterministic generator, which recomputes the
  live numbers from `ROADMAP.md` + `STATUS.md` and patches the page in place.

Source of truth is always the markdown. This skill only ever *reads* it and
*writes* the HTML.

## Workflow

### Lane: open
```bash
f=docs/goal/goal-overview.html
if grep -qi microsoft /proc/version 2>/dev/null; then
  # WSL2: xdg-open has no handler — open via the Windows host (explorer.exe works here)
  explorer.exe "$(wslpath -w "$f")" 2>/dev/null \
    || cmd.exe /c start "" "$(wslpath -w "$f")" 2>/dev/null \
    || powershell.exe -NoProfile -Command "Start-Process '$(wslpath -w "$f")'"
else
  xdg-open "$f" >/dev/null 2>&1 &
fi
```
Report the path. **On WSL2, `xdg-open` silently fails** (no Linux browser handler) — always route through the Windows host (`explorer.exe` with `wslpath -w`). If no opener works, give the operator the path to open manually. Note `explorer.exe` returns rc=1 even on success.

### Lane: update
1. **Run the generator** from repo root:
   ```bash
   python3 .claude/skills/status/scripts/build_goal_overview.py
   ```
2. **Report its summary** — the changed fields (`artifact-data JSON`,
   `gen:roadmap_totals`, `meters[...]`, etc.) and the new totals line. If it
   prints "no change — already in sync", say so plainly.
3. **On a non-zero exit, stop and surface the error verbatim** — it means a
   required file or `<!-- gen:NAME -->` marker is missing, or `STATUS.md`'s
   Current Position is unparseable. Fix the source, do not hand-edit the HTML.
4. Offer to `/status open` the refreshed page.

The generator owns all parsing/patching logic (CP4: deterministic logic lives in
`scripts/`, not here). Read it only when changing what gets synced.

## Hard rules

1. **Never hand-edit the live numbers in `goal-overview.html`.** Run the
   generator — hand edits are non-idempotent and re-drift on the next run.
2. **`ROADMAP.md` / `STATUS.md` are the source of truth — never write them from
   this skill.** Update flows one way: markdown → HTML.
3. **Never touch hand-authored narrative prose.** The generator only rewrites the
   `#artifact-data` block, `<!-- gen:NAME -->` marker regions, and per-milestone
   meters. If a number lives outside those, add a marker — don't free-edit.
4. **Trust the generator's exit code.** Non-zero = real problem (missing
   file/marker, unparseable STATUS). Surface it; never paper over it by editing
   the HTML directly.
5. **Counting semantics are the generator's, not a naive grep.** Closed/open =
   `[x]`/`[ ]` *occurrences within milestone sections* (from the first
   `### M<x.y>` onward), not whole-file line counts.

## CLOSEOUT (every run)

1. **Update lane**: confirm the generator exited 0 and report the change summary
   (or "no change"). Re-run with `--check` to prove idempotency if you patched.
2. **Open lane**: confirm the browser launch command was issued + report the path.
3. **Staleness scan** (when editing this skill): verify
   `scripts/build_goal_overview.py` exists and the four `<!-- gen:* -->` markers
   (`snapshot_date`, `epoch`, `milestone`, `roadmap_totals`) still exist in
   `goal-overview.html`; grep that the `#artifact-data` block is still present.
   If markers were removed, the generator will fail loudly — restore them.

## Reference

- Generator: [`scripts/build_goal_overview.py`](scripts/build_goal_overview.py)
  — parsing rules + patch targets + `--check` idempotency flag.
- Source of truth: `docs/goal/ROADMAP.md`, `docs/goal/STATUS.md`.
- Artifact: `docs/goal/goal-overview.html` (untracked; hand-authored prose + generated numbers).
