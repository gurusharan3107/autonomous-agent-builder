# hermes-chrome — Best Practices

Skill-specific defaults and conventions. Read on first use; internalize.
The SKILL.md `Hard rules` + `Workflow` section captures the *what*; this
file captures the *why* and the calibration around each rule.

---

## Default to compact: `page_context` first, always

`page_context` is ~1 KB. `snapshot` is 3–8 KB (a `<button>`-heavy page can hit 30 KB). Both answer "what's on the page" but at different costs.

**Rule:** never open a turn with `snapshot`. Run `page_context` first. Escalate to `snapshot` only when you need a CSS selector for an element that `page_context` doesn't surface (i.e. not a heading, nav link, button, or input).

For visual proof of a specific region, `zoom {x0,y0,x1,y1}` returns a focused region — 2–10 KB — preferable to a full `screenshot` (50–200 KB). Use `screenshot` only when whole-page layout is the evidence you need.

---

## Batch actions in one `bridge()` call

Each `bridge()` is a socket round-trip with native-messaging serialization on top. Two actions in one call ≈ one action; ten actions ≈ slightly more than one. The cost scales with the number of *calls*, not the number of *actions*.

```python
# Bad — three round-trips
bridge({"actions":[{"type":"goto","url":"..."}]})
bridge({"actions":[{"type":"wait_for_selector","selector":"h1"}]})
bridge({"actions":[{"type":"page_context"}]})

# Good — one round-trip, same outcome
bridge({"actions":[
  {"type":"goto","url":"..."},
  {"type":"wait_for_selector","selector":"h1","timeout":5000},
  {"type":"page_context"}
]})
```

Compound patterns in [`operate.md`](operate.md#compound-patterns) are written this way for a reason.

---

## `useSelectedTab` — pick the right value

| Use `True` when… | Use `False` when… |
|---|---|
| You're continuing in a tab you already opened | First action of a session |
| The operator pointed you at a specific tab | Active tab is `chrome://`, `about:*`, or an error page |
| You're verifying after a previous action | You don't know the current tab state |

Default: **start with `False` + `goto`** for the first action of a session. Switch to `True` for subsequent actions in the same tab.

When `True` fails with "Tab is no longer available" or "Content script blocked", recover with `False` + `goto`. See [`operate.md` §Blocked URL recovery](operate.md#blocked-url-recovery).

---

## Click semantics — cursor only

Hard rule from SKILL.md: every interaction goes through the visible cursor. The why:

- The animated cursor lets the **operator** follow what the agent is doing. Silent JS clicks via `evaluate` are invisible — bad for trust, worse for debugging.
- `click_text` / `click_selector` walk the same event path a real click does (mouseDown → mouseUp → click → focus). `evaluate` synthesizing a click bypasses focus tracking and many event handlers.
- Cursor clicks resolve through `elementAtPoint` — they catch overlays/popovers naturally. `evaluate` clicks on a hidden node won't.

**Selectors:** prefer `click_text` for buttons/links (no fragile selectors). Use `click_selector` when text isn't unique. Use `cursor_*` (raw coordinates) only when both fail.

---

## `wait_for_selector` beats fixed `wait`

Network and SPA render times vary. A fixed `wait` either over-waits (slow) or under-waits (flaky). `wait_for_selector` returns the instant the element appears, with a generous timeout as a safety net.

```python
# Bad — over-waits 5 s every time
{"type":"goto","url":"..."}, {"type":"wait","ms":5000}, {"type":"page_context"}

# Good — returns as soon as the page is ready, up to 5 s
{"type":"goto","url":"..."}, {"type":"wait_for_selector","selector":"h1","timeout":5000}, {"type":"page_context"}
```

---

## `session_name` groups tabs but does NOT isolate the socket

Pass `sessionName` to keep all tabs from one task in a single Chrome tab group (visual hygiene for the operator). It does **not** isolate the bridge socket — see the multi-Claude-session lesson in [`agent-handbook.md`](agent-handbook.md). If you need tab isolation, use `useSelectedTab: False` + `goto` to open a fresh tab.

---

## Report every turn — the operator follows your words

If you take an action and don't describe it, the operator sees Chrome flicker and has no idea why. After each `bridge()` call, in your turn output: state what you did, what you observed, what's next.

For multi-step workflows, also state the plan up front: *"Going to: navigate → fill the form → submit → verify."* Then the operator can predict what each Chrome flicker means.

---

## Closeout is a discipline, not a nice-to-have

The SKILL.md closeout requires four things every run: screenshot, final URL/title, bridge health, tab cleanup. Skipping any of them leaves Chrome in a state the next agent (or human operator) will trip over:

- No screenshot → no evidence the run did what it claimed
- No final URL → the operator doesn't know where they are
- No bridge health check → next agent inherits a dead socket
- No tab cleanup → Chrome accumulates dozens of orphan tabs across sessions

If the run fails mid-way, **still** run closeout. Report what failed; document the final state honestly; clean what you can. Incomplete is better than dishonest.

---

## When to enter Optimize vs keep trying

Enter [`optimize.md`](optimize.md) when:
- Socket error on connect / preflight exit 1
- Same action fails twice with the same error
- `page_context` returns clearly wrong / empty data despite a healthy bridge
- Cursor visible flickers but the click doesn't register

Don't enter Optimize for:
- A single action timing out (try once more; many SPAs hiccup)
- The active tab being `chrome://` (just use `useSelectedTab: False` + `goto`)
- A different tab than expected (another Claude session — explicit `goto` recovers)

The cost of an unnecessary Optimize entry is high: it loads ~440 lines of additional context.

---

## Token efficiency — what to cut, what to keep

Cut:
- Wait-and-re-read patterns (use `wait_for_selector` instead)
- Full `screenshot` when `zoom` of one region would do
- Repeated `page_context` calls in a tight loop (one per significant state change)
- `snapshot` when `page_context` would suffice

Keep:
- The post-action verification `page_context` — silent successes are dangerous
- The closeout screenshot — visible proof matters
- Reporting prose in the agent's turn output — token-cheap, trust-expensive to skip
