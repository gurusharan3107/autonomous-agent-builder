# hermes-chrome — Operate reference

Full action reference and patterns. Loaded on demand from SKILL.md.

## All actions

```python
# Level 1 — compact page overview
{"type": "page_context"}
# → {url, title, headings:[{tag,text}], nav:[{text,href}], buttons:[str], inputs:[{name,type,value}]}

# Level 2 — full visible text
{"type": "text"}
# → {url, title, text}

# Level 3 — interactive element list (no div/span duplication)
{"type": "snapshot"}
# → {url, title, element_count, snapshot:[{i,tag,role,text,href,value?,input_type?,name?}]}

# Navigate (waits 2s by default; set waitMs to override)
{"type": "goto", "url": "https://example.com"}
{"type": "goto", "url": "https://example.com", "reload": True}  # force reload

# Click by visible text — finds element, animates cursor, clicks
{"type": "click_text", "text": "Submit"}
# → {type, text, point: {x, y, tag, text}}

# Click by CSS selector — animates cursor
{"type": "click_selector", "selector": "#submit-btn"}

# Fill a field (clicks to focus, then types; append:true adds without clearing)
{"type": "fill_selector", "selector": "#email", "value": "user@example.com"}
{"type": "fill_selector", "selector": "#note", "value": " extra", "append": True}

# Screenshot — JPEG by default, always under 1MB native-messaging limit
{"type": "screenshot"}
# → {format:"jpeg", screenshot_path:"~/.hermes/cache/hermes-chrome/<id>.jpeg"}
{"type": "screenshot", "format": "png"}   # explicit PNG if needed

# Explicit pause
{"type": "wait", "ms": 500}

# Evaluate arbitrary JS
{"type": "evaluate", "expression": "document.title"}
# → {type, result: <value>}

# Close a managed tab (skip when useSelectedTab:true)
{"type": "close_tab"}
```

## Cursor control (coordinate-level)

Prefer `click_text` / `click_selector` — they find, animate, and click in one step.
Use raw cursor actions only when coordinate-level control is required.

```python
{"type": "cursor_move", "x": 400, "y": 200}
{"type": "cursor_click"}
{"type": "cursor_right_click"}
{"type": "cursor_double_click"}
{"type": "cursor_triple_click"}
{"type": "cursor_type", "text": "hello"}
{"type": "cursor_key", "key": "Enter", "modifiers": []}        # modifiers: ctrl, shift, alt, cmd
{"type": "cursor_drag", "x": 600, "y": 300, "duration": 500}
{"type": "cursor_scroll", "deltaX": 0, "deltaY": 300}
{"type": "cursor_status"}   # → {visible, x, y, phase, url, title}
{"type": "cursor_hide"}
```

## Compound patterns

### Page audit
```python
actions=[{"type":"page_context"}, {"type":"screenshot"}]
```

### Navigate + confirm
```python
actions=[
    {"type":"goto","url":"https://app.example.com"},
    {"type":"page_context"}
]
```

### Fill form + submit + verify
```python
actions=[
    {"type":"fill_selector","selector":"#email","value":"user@example.com"},
    {"type":"fill_selector","selector":"#password","value":"secret"},
    {"type":"click_text","text":"Sign in"},
    {"type":"wait","ms":1000},
    {"type":"page_context"}
]
```

### Find selector then click
```python
# Step 1 — get snapshot to locate element
r = bridge({"type":"run","useSelectedTab":True,"actions":[{"type":"snapshot"}]})
# Step 2 — click by text found in snapshot
actions=[{"type":"click_text","text":"<text from snapshot>"}]
```

### Click + visual proof
```python
actions=[
    {"type":"click_text","text":"Download"},
    {"type":"wait","ms":800},
    {"type":"screenshot"}
]
```

## Efficiency rules

- One `bridge()` call per task — batch everything.
- `page_context` first; escalate to `snapshot` only when you need a selector.
- One state check after click/fill is enough.
- `screenshot` only when visual layout matters.
- Skip `goto` if already on the correct URL.
- Do not retry a failed selector — get a fresh `snapshot` first.
- Do not spin on a dead bridge. If a call times out, do **one** `status` retry after a fix (extension reload / sync), then go to Optimize — never loop blind retries.
- For local-artifact proof, serve over `http://127.0.0.1:<port>/`; avoid `file://` unless extension file access is intentionally enabled.

## Closeout

Mandatory, in order. Goal: the next agent doing browser testing finds Chrome in
a known-good state — visible window, sane page, live bridge, no orphaned tabs.

```python
# 1+2+3 in one batched call: proof, final location, bridge health
r = bridge({"type":"run","useSelectedTab":True,"actions":[
    {"type":"screenshot"},
    {"type":"page_context"}
]})
status = bridge({"type":"status","timeoutSeconds":5})
```

1. **Final screenshot** — `screenshot`; report `screenshot_path` as visual proof
   of the end state.
2. **Final URL + title** — from `page_context`; state where you left the browser.
3. **Bridge health re-check** — `status` returns `success: true`. If not,
   enter Optimize → [optimize.md](optimize.md); do not declare the run done.
4. **Tab cleanup** — `close_tab` for any tab *you* opened during the run. Leave
   the operator's `useSelectedTab` tab in place, on a sane page (not an error
   page, not `about:blank`, not a half-filled form). Navigate it back to the
   starting URL recorded at preflight if the run left it somewhere unexpected.
5. **Handoff line** — one line: "Chrome left at <url>, bridge ready, N tabs
   closed — known-good for next agent."

**Failure states (report honestly, do not paper over):**

- **Bridge died mid-run** — socket error or `ready: false` at closeout. Report it
  and route to Optimize; the next agent must not assume a live bridge.
- **Left on an error/blank page** — navigate back to a sane page before handoff,
  or flag it explicitly if you cannot.
