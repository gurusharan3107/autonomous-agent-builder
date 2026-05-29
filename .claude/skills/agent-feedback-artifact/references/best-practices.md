# agent-feedback-artifact — Best Practices

Skill-specific conventions and defaults. Read on first use, internalize, then
the SKILL.md per-marker quick-reference is enough.

---

## Per-marker decision rubric (the one you make every wake)

| Branch | Action |
|---|---|
| `route: no_worker_main_agent_direct` AND summary unambiguous | Act directly on summary. **Skip** `agent-feedback-details.mjs`. |
| `route: no_worker_main_agent_direct` BUT summary vague (e.g. "fix this", "change it") | Pull details once via `agent-feedback-details.mjs <id> --root <root>`. |
| `route: deep_marker_worker` | Pull details. The marker likely affects data/computation, not styling. |
| `route: cheap_marker_worker` | Default route — usually means routing classifier didn't recognize intent. Act on summary; if unclear, pull details. Consider adding the missing keyword to `agent-feedback-routing.mjs` after handling. |

**Why this matters:** pulling details adds ~50 ms RTT + ~2 KB to context per marker. Across a session of N markers, this compounds. The wake payload (~250 chars) is designed to be sufficient for the dominant case.

---

## Reload-flag choice

`mark.mjs` accepts an optional reload flag that tells the widget how to surface the change.

| Flag | What the widget does | When to use |
|---|---|---|
| `--reload` | **CSS hot-swap** — replaces every `<link rel="stylesheet">` with a cache-busted clone. ~400–700 ms to visible change. No page reload, no JS state loss. | Every CSS/styling edit (color, font, spacing, layout, badges). Dominant case. |
| `--reload-full` | **Full page reload** — `location.replace` with a cache-bust query param. ~700 ms + Chrome HTML parse/render. Resets all runtime JS state. | HTML / template / JSX / Jinja2 edits — anything that changes DOM structure server-side. |
| *(none)* | Reply only, no auto-refresh. | Question-only replies, ambiguous "should I change anything?" responses. |

**Default:** `--reload`. CSS edits are the dominant case; the worst-case fallout of using `--reload` when you should have used `--reload-full` is the operator pressing F5 once. The reverse (`--reload-full` for a CSS-only change) wastes their runtime state.

---

## Batching concurrent markers

If a new wake notification arrives while you're still processing a previous marker, **fold the new one into the same turn**. Do not sequentially mark-done one-at-a-time.

Measured ~2× wall-clock savings on 3 markers vs. one-per-turn. The savings come from amortizing your LLM inference + tool-call overhead across multiple actions.

When batching:
- Process all markers' actions before any mark.mjs call (collect edits, then mark them all done together).
- If two markers target the SAME element with conflicting intents (e.g. "make blue" then "make red"), the later one wins; mark the earlier as done with a note ("overridden by your follow-up").
- If one marker requires `--reload` and another `--reload-full`, only the strongest matters — the widget escalates to `--reload-full` if any pending marker requests it.

---

## Routing classifier — what it does, how to extend

`agent-feedback-routing.mjs` exposes `classifyWorkItem(item)` which returns `{route, contextTier, workerLifecycle, model, reasoningEffort, reason}`. The agent doesn't need to call this directly — the server attaches the route to every queue item.

| `route` | Meaning |
|---|---|
| `no_worker_main_agent_direct` | Style intent. Main agent acts directly. Cheapest path. |
| `cheap_marker_worker` | Default fallback. Treat like the direct path but with extra caution; consider keyword expansion. |
| `deep_marker_worker` | Data/calc intent. Spawn a fresh-once worker with bounded packet. |

**Selector is evidence, not intent** — never classify by `data-*` attributes or CSS classes alone. Intent comes from the comment text.

**Extending the keyword list:** when a marker mis-routes, add the missing keyword(s) to `styleIntent` (style/UI words) or `dataIntent` (calc/data words) in `agent-feedback-routing.mjs`. Re-test the same marker. The list is intentionally append-only and grown by experience.

---

## Token / context efficiency rules

1. **Wake payload first, details second.** The Monitor notification carries `{id, route, summary, sentAt, createdAt, emittedAt}` — usually enough to act. Don't auto-pull details "just to be sure."
2. **Mark with the right reply length.** The reply field shows in the operator's widget status bar — keep it under ~140 chars (~the wake summary's slice limit). Long agent justifications belong in commit messages or chat, not the marker reply.
3. **Don't poll.** The wake source is push (kernel `fs.watch` → SSE). If you find yourself running `agent-feedback-next.mjs` in a loop, the Monitor isn't armed correctly — fix that.
4. **Batch.** Two markers in one turn is cheaper than two turns. See above.
5. **Skip `agent-feedback-status.mjs` between marks.** The next wake will tell you about the next marker; you don't need to ask the server "what else?"

---

## Operator-facing reply conventions

- Lead with the change: `"VELOCITY value → teal #00d4d4 via CSS hot-swap."` not `"I have applied the requested change."`
- Name the file you edited: `"…edited app/static/styles.css."` so the operator can audit.
- For overrides, name the new winner: `"Overridden by your follow-up to make it yellow."`
- For questions back, end with the prompt: `"Which page should this apply to — the dashboard or every page?"`

The reply shows in the widget's top-right status bar. Operators see it in real time via SSE.

---

## Critical-arg defaults

- **`--root` is required** for every script that reads/writes the queue: `agent-feedback-next.mjs`, `agent-feedback-details.mjs`, `agent-feedback-mark.mjs`, `agent-feedback-watch.mjs`, `agent-feedback-closeout.mjs`. Use the same path you passed to `artifact-feedback-server.mjs`.
- **`--port` defaults to 4177** for server + preflight + closeout. Match across all three.
- **`QUEUE_ORIGIN` defaults to `http://localhost:4177`** in the extension widget. Don't change to `127.0.0.1` — see WSL2 IPv6 note in [`agent-handbook.md`](agent-handbook.md).
