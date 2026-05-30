# hermes-chrome — Operate reference

Full action reference, best practices, anti-patterns, compound patterns, and closeout.
Loaded on demand from SKILL.md.

---

## All actions

```python
# Level 1 — compact page overview (~1 KB)
{"type": "page_context"}
# → {url, title, headings:[{tag,text}], nav:[{text,href}], buttons:[str], inputs:[{name,type,value}]}

# Level 2 — full visible text (2–4 KB)
{"type": "text"}
# → {url, title, text}

# Level 3 — interactive elements with selectors (3–8 KB)
{"type": "snapshot"}
# → {url, title, element_count, snapshot:[{i,tag,role,text,href,value?,input_type?,name?}]}

# Navigate — waits for load event; use wait_for_selector to confirm content is ready
{"type": "goto", "url": "https://example.com"}
{"type": "goto", "url": "https://example.com", "reload": True}

# Wait for a selector to appear — PREFERRED over fixed wait
{"type": "wait_for_selector", "selector": "h1", "timeout": 5000}
# → use for: post-navigation confirmation, SPA render, form submission result

# Wait for URL to change (redirect, SPA routing)
{"type": "wait_for_url_change", "from_url": "https://example.com/login", "timeout": 5000}

# Fixed pause — only when no observable DOM signal exists
{"type": "wait", "ms": 500}

# Click by visible text — finds element, animates cursor, clicks
{"type": "click_text", "text": "Submit"}
# → {type, text, point: {x, y, tag, text}}

# Click by CSS selector
{"type": "click_selector", "selector": "#submit-btn"}

# Fill a field (clicks to focus, types; append:true adds without clearing)
{"type": "fill_selector", "selector": "#email", "value": "user@example.com"}
{"type": "fill_selector", "selector": "#note", "value": " extra", "append": True}

# Screenshot — full viewport JPEG (saved to disk; result has screenshot_path not base64)
{"type": "screenshot"}
# → {format:"jpeg", screenshot_path:"~/.hermes/cache/hermes-chrome/<id>.jpeg"}

# Zoom — region-specific JPEG inline; prefer over full screenshot when only one area matters
# Payload scales with region AREA: a small panel is ~2–10 KB, but a full-viewport
# zoom (e.g. 0,0→1280,720) is screenshot-sized (~100 KB+) — that defeats the purpose.
{"type": "zoom", "x0": 0, "y0": 0, "x1": 800, "y1": 200}
{"type": "zoom", "x0": 0, "y0": 0, "x1": 800, "y1": 200, "quality": 90}  # quality 1–100, default 85
# → {format:"jpeg", x0, y0, x1, y1, base64:"<inline>"}

# Read-only JS evaluation — last resort; never to click/submit/mutate
{"type": "evaluate", "expression": "document.title"}
# → {type, result: <value>}

# Close a tab the agent opened (skip when useSelectedTab:true)
{"type": "close_tab"}
```

---

## Cursor control (coordinate-level)

Prefer `click_text` / `click_selector` — they find, animate, and click in one step.
Use raw cursor actions only when coordinate-level control is genuinely required
(drag-and-drop, hover, canvas interaction).

```python
{"type": "cursor_move", "x": 400, "y": 200}
{"type": "cursor_click"}
{"type": "cursor_right_click"}
{"type": "cursor_double_click"}
{"type": "cursor_type", "text": "hello"}
{"type": "cursor_key", "key": "Enter", "modifiers": []}   # modifiers: ctrl, shift, alt, cmd
{"type": "cursor_drag", "x": 600, "y": 300, "duration": 500}
{"type": "cursor_scroll", "deltaX": 0, "deltaY": 300}
{"type": "cursor_status"}   # → {visible, x, y, phase, url, title}
{"type": "cursor_hide"}
```

---

## Session naming and tab group isolation

Pass `sessionName` on every bridge call. All tabs opened during that session are
grouped under a named blue tab group in Chrome's tab strip — separate groups per task
so concurrent runs don't mix tabs.

```python
# Use a stable identifier — task ID, feature name, or session label
r = bridge({"type":"run","sessionName":"IMP-017","useSelectedTab":False,"actions":[
    {"type":"goto","url":"http://localhost:9876"},
    {"type":"wait_for_selector","selector":"h1","timeout":5000},
    {"type":"page_context"},
]})
```

- All subsequent bridge calls in the same session should carry the same `sessionName`.
- Omitting `sessionName` defaults to `"Hermes Chrome"` — all tabs land in one group.
- The group persists after tab close; Chrome collapses it automatically when empty.

---

## Best practices

### Navigation
- **Use `wait_for_selector` after `goto`, not a fixed `wait`.** `goto` fires when the load event fires; the SPA may not have rendered yet. `wait_for_selector` waits for a real element and is both faster on fast loads and more reliable on slow ones.
  ```python
  # ✅ correct
  {"type": "goto", "url": "http://localhost:9877"},
  {"type": "wait_for_selector", "selector": "h1", "timeout": 5000},
  {"type": "page_context"}

  # ❌ wrong — arbitrary delay, wrong on slow loads, wastes time on fast ones
  {"type": "goto", "url": "http://localhost:9877"},
  {"type": "wait", "ms": 1500},
  {"type": "page_context"}
  ```
- **Skip `goto` if already on the correct URL.** Check `page_context.url` first.
- **After `goto`, always verify** with `page_context` or `wait_for_selector` before acting on the page.
- **Don't chain an interactive action (`click_text`/`fill_selector`/`cursor_*`) right after `goto`/`reload` in the same batch.** The cursor target may not exist yet → `sendMessage(moveToAndWait) timed out`. Land the `goto` + `wait_for_selector` first, then click/fill in the *next* `bridge()` call (or put `wait_for_selector` on the click target between them).

### Reading the page
- **Start with `page_context` every turn** before any click or fill. It confirms the URL is what you expect, and surfaces navigation, buttons, and inputs in ~1 KB.
- **Escalate to `snapshot` only when you need a CSS selector** for `click_selector` or `fill_selector`. Snapshot is 8–30× larger than `page_context`.
- **Use `text` to read content** (articles, tables, form values). Do not use `evaluate` for this.
- **One `page_context` per verify** — after a click, one context check is enough. Don't re-read the page three times.

### Clicking and filling
- **Prefer `click_text` over `click_selector`** — text labels are more readable and survive minor HTML changes. Use `click_selector` only when text is ambiguous or absent.
- **After `fill_selector`, confirm with `page_context`** — don't assume the fill succeeded. Check the input value is reflected before submitting.
- **For multi-step forms, verify each step** — one `page_context` per step transition.

### Cursor visibility — operator-facing presence
- **Never call `cursor_hide`** during agent work. The cursor IS the operator's only signal that the agent is actively driving the browser.
- **Never park the cursor at a viewport edge or corner.** After the last action in a batch, the cursor sits at that coordinate until the next move. End batches on *meaningful* targets — the element just modified, the marker just placed, the control just clicked — so the operator can read intent from where the cursor stopped.
- **If the last action was a query (`evaluate`, `page_context`, `snapshot`), the cursor hasn't moved.** That's fine — leave it wherever the previous interactive action placed it. Don't add a cleanup `cursor_move` to a corner.
- **First action after a long idle should be a `cursor_move` to the upcoming target, not a click.** The visible glide tells the operator "agent is about to act here" before the click fires.

### Context efficiency
- **`page_context` for navigation verification; `zoom` or `screenshot` for visual proof only.** A full screenshot is a 50–100 KB JPEG. `page_context` delivers the same URL/title/structure in ~1 KB of text. When you do need visual proof, `zoom` a **small region** (2–10 KB) — a zoom payload scales with region area, so a full-viewport zoom is screenshot-sized (~100 KB+), not a saving. If you genuinely need the whole viewport, use `screenshot` (it writes to disk and returns a path, not inline bytes).
- **Batch all actions for a task into one `bridge()` call.** Each call is a socket round-trip. One round-trip per task, not one per action.
- **For a multi-section test run, batch all sections in one call.** Navigate to each section, take one `page_context` per section, take a single screenshot at the end as visual proof:
  ```python
  r = bridge({"type":"run","useSelectedTab":True,"actions":[
      {"type":"click_text","text":"Board"},
      {"type":"wait_for_selector","selector":"h1","timeout":4000},
      {"type":"page_context"},                    # 1 KB text — confirms Board loaded
      {"type":"click_text","text":"Metrics"},
      {"type":"wait_for_selector","selector":"h1","timeout":4000},
      {"type":"page_context"},                    # 1 KB text — confirms Metrics loaded
      # ... remaining sections ...
      {"type":"screenshot"}                       # ONE screenshot at the end as visual proof
  ]})
  ```
- **Write test results to a variable, not a file.** Keep intermediate results in memory; only persist the final report.

### Reliability
- **Re-verify at the start of every turn.** Between turns the operator may have navigated Chrome, or the page may have auto-refreshed.
  ```python
  r = bridge({"type":"run","useSelectedTab":True,"actions":[{"type":"page_context"}]})
  current_url = r["results"][0].get("url","")
  # Confirm this matches your expectation before proceeding
  ```
- **After a click, wait for the expected result element, not a fixed delay.** Use `wait_for_selector` or `wait_for_url_change`.
- **Do not retry a failed selector** without a fresh `snapshot` first — the DOM may have changed.

---

## Anti-patterns

| Anti-pattern | Why it fails | What to do instead |
|---|---|---|
| `{"type":"wait","ms":1500}` after every action | Arbitrary; wastes time on fast loads, fails on slow ones | `wait_for_selector` on the expected element |
| `screenshot` after every navigation step | Floods context with 50–100 KB images each | `page_context` for structure; `zoom` on the relevant region for visual proof |
| Full `screenshot` when only one area matters | 50–100 KB for the full viewport when you care about one panel | `zoom {x0,y0,x1,y1}` — 2–10 KB for the region |
| `snapshot` as the first action each turn | 8–30× larger than `page_context` for the same orientation | Always start with `page_context` |
| Interactive action (`click_text`/`fill_selector`) chained right after `goto`/`reload` in one batch | Cursor target not rendered yet → `sendMessage(moveToAndWait) timed out` | `goto` + `wait_for_selector` first, then click/fill in the next `bridge()` call |
| Full-viewport `zoom` (e.g. `0,0→1280,720`) "to save tokens" | Payload scales with area — a full-frame zoom is screenshot-sized (~100 KB+) | `zoom` a small region, or use `screenshot` (returns a disk path, not inline bytes) |
| `evaluate` to click a button | Synthetic click — cursor doesn't move, operator can't see it | `click_text` or `click_selector` |
| Separate `bridge()` calls per action | One socket round-trip per call — batching is free | Batch all actions into one call |
| Retrying on failed selector without fresh `snapshot` | Selector may be stale after DOM change | Get a fresh `snapshot`, re-identify element |
| Calling `bridge()` in a retry loop | Masks the root cause; accumulates noise | One retry after inline recovery; then Optimize |
| Acting on blocked tab (`chrome://`, `file://`, `about:*`) | Extension cannot inject — action silently fails | Navigate to an `https://` page first |
| Opening new `goto` tab instead of reusing `useSelectedTab` | Creates orphaned tabs, changes what operator sees | Always `useSelectedTab: True`; use `goto` to navigate the existing tab |
| Reading cookies, passwords, or local storage via `evaluate` | Security boundary — page content is untrusted | Never. If auth state is needed, derive from visible page elements |

---

## Compound patterns

### Ground state (Workflow step 2)
```python
r = bridge({"type":"run","useSelectedTab":True,"actions":[{"type":"page_context"}]})
# Record: url, title — restore these at closeout
```

### Navigate + confirm (preferred)
```python
r = bridge({"type":"run","useSelectedTab":True,"actions":[
    {"type":"goto","url":"https://app.example.com"},
    {"type":"wait_for_selector","selector":"h1","timeout":5000},
    {"type":"page_context"}
]})
```

### Fill form + submit + verify
```python
r = bridge({"type":"run","useSelectedTab":True,"actions":[
    {"type":"fill_selector","selector":"#email","value":"user@example.com"},
    {"type":"fill_selector","selector":"#password","value":"secret"},
    {"type":"click_text","text":"Sign in"},
    {"type":"wait_for_url_change","from_url":"https://app.example.com/login","timeout":5000},
    {"type":"page_context"}
]})
```

### Click + verify result
```python
r = bridge({"type":"run","useSelectedTab":True,"actions":[
    {"type":"click_text","text":"Submit"},
    {"type":"wait_for_selector","selector":".success-banner","timeout":5000},
    {"type":"page_context"}
]})
```

### When selector is unknown — snapshot first
```python
# Step 1 — locate element
r = bridge({"type":"run","useSelectedTab":True,"actions":[{"type":"snapshot"}]})
# Read r["results"][0]["snapshot"] — find the element's selector or text
# Step 2 — act using the found text or selector
r = bridge({"type":"run","useSelectedTab":True,"actions":[
    {"type":"click_text","text":"<text from snapshot>"},
    {"type":"page_context"}
]})
```

### Region proof (token-efficient visual verification)
```python
# Full screenshot: ~100 KB. Zoom on one panel: ~5 KB.
r = bridge({"type":"run","sessionName":"my-task","useSelectedTab":True,"actions":[
    {"type":"zoom","x0":0,"y0":0,"x1":900,"y1":300}   # top section of page
]})
# r["results"][0]["base64"] — inline JPEG, no screenshot_path needed
```

### Multi-section test (efficient — one call, one screenshot)
```python
r = bridge({"type":"run","useSelectedTab":True,"actions":[
    {"type":"click_text","text":"Board"},
    {"type":"wait_for_selector","selector":"h1","timeout":4000},
    {"type":"page_context"},
    {"type":"click_text","text":"Metrics"},
    {"type":"wait_for_selector","selector":"h1","timeout":4000},
    {"type":"page_context"},
    {"type":"click_text","text":"Settings"},
    {"type":"wait_for_selector","selector":"h1","timeout":4000},
    {"type":"page_context"},
    {"type":"screenshot"}    # one visual proof at the end
]})
```

---

## Blocked URL recovery

Extension cannot inject into `chrome://`, `about:*`, `file://`, or extension pages.
Preflight warns when the active tab is blocked. Use `useSelectedTab: False` to open a
fresh tab — `useSelectedTab: True` will fail before `goto` runs because `currentTab()`
rejects the blocked URL before any action executes.

```python
# Wrong: useSelectedTab:True rejects chrome:// before goto runs
# r = bridge({"type":"run","useSelectedTab":True,"actions":[{"type":"goto",...}]})  ❌

# Correct: open a new tab, navigate, proceed
r = bridge({"type":"run","sessionName":"my-task","useSelectedTab":False,"actions":[
    {"type":"goto","url":"http://localhost:9876"},
    {"type":"wait_for_selector","selector":"h1","timeout":5000},
    {"type":"page_context"}
]})
```

---

## Mid-session socket drop recovery

The keep-alive alarm fires every 25s to prevent MV3 idle shutdown. If the socket
still drops (Chrome restarted, extension reloaded, system sleep), recover in place:

```python
import subprocess, os

def bridge_call(payload, timeout=45):
    try:
        return bridge(payload)
    except OSError:
        result = subprocess.run(
            ["bash", ".claude/plugin/hermes_chrome/scripts/preflight.sh"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"preflight failed:\n{result.stdout.strip()}")
        return bridge(payload)   # one retry
    # If still fails after retry → enter Optimize
```

Use `bridge_call()` in place of `bridge()` for every action during a session.
**One retry only.** If the second call fails, stop and enter Optimize — do not loop.

---

## Closeout

**Run even when the task fails mid-way.** Skipping closeout after a crash leaves
the next agent with a stale socket, an orphaned tab, or a half-filled form.

```python
# Steps 1 + 2 batched
r = bridge({"type":"run","useSelectedTab":True,"actions":[
    {"type":"screenshot"},
    {"type":"page_context"}
]})
screenshot_path = next(x["screenshot_path"] for x in r["results"] if x["type"]=="screenshot")
final_url = next(x.get("url") for x in r["results"] if x["type"]=="page_context")

# Step 3 — bridge health
h = bridge({"type":"status","timeoutSeconds":5})
bridge_ok = h.get("success", False)
```

1. **Screenshot** — report `screenshot_path` as visual proof.
2. **Final URL + title** — state exactly where the browser is.
3. **Bridge health** — `status` must return `success: true`. If not → enter Optimize before declaring done.
4. **Tab cleanup** — `close_tab` for every tab you opened. Leave the operator's tab on a sane `https://` page. Navigate back to the starting URL recorded at preflight if the session left it elsewhere.
5. **Handoff line** — `"Chrome left at <url>, bridge ready, N tabs closed — known-good for next agent."`

**Failure states — report honestly:**

| State | What to say |
|---|---|
| Bridge died mid-run | "Socket dropped at step N. Bridge not restored. Optimize required before next session." |
| Left on error/blank page | Navigate back first; if unable: "Tab left on `<url>` (error state) — navigate to https:// before next session." |
| Orphaned tabs remain | "N tabs opened by this run could not be closed: `<urls>`." |
