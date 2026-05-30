# chrome-extension-author — Operate

Full procedure for scaffolding a Chrome MV3 extension. Loaded on demand from SKILL.md.

```
Interview → Plan → Scaffold → Verify → Print install + test instructions
```

## 1. Interview

Run the questions in [`interview.md`](interview.md). Two `AskUserQuestion` batches:

- **Batch A** (4 questions, one call): purpose, architecture pieces, visual presence, native messaging.
- **Batch B** (4 questions, one call): icon style, permissions scope, storage, lifecycle trigger.

Pre-fill any answer the operator's typed prompt already names. Echo the final answer set back as a short summary table before moving on — operator gets to redirect any wrong inference in one turn.

## 2. Plan

Build the file list from the answers. Defaults:

| Answer | Files added to plan |
|---|---|
| Architecture: SW only | `manifest.json`, `service_worker.js` |
| + Content scripts | + `content-scripts/main.js` |
| + Popup | + `popup.html`, `popup.js`, `popup.css` |
| + Native messaging | + `native/host.py`, `native/host.json`, `native/install.sh` |
| Visual presence: overlay cursor | + `content-scripts/cursor.js` (hardened per [`visual-presence.md`](visual-presence.md)) |
| Visual presence: toast | + small toast helper inside the content-scripts entry |
| Storage: chrome.storage | adds `"storage"` to permissions; SW uses `chrome.storage.local` |
| Storage: localStorage | content scripts include `safeParseArray` helper |
| Lifecycle: auto on navigation | SW registers `chrome.tabs.onUpdated` with re-inject pattern + URL guards |
| Lifecycle: alarms | SW uses `chrome.alarms` instead of timers |
| Always | `scripts/validate.sh`, `images/icon.svg` + 16/32/48/128 PNGs, `agent-handbook.md` for the *generated* extension |

Print the plan as a tree. Get one-line confirmation from the operator before writing.

## 3. Scaffold

Target directory default: `extensions/<extension-name>/` at the repo root (NOT inside `.claude/`). Operator can override.

```bash
EXT_NAME="<kebab-case-name>"
EXT_DIR="extensions/${EXT_NAME}"
TPL_DIR=".claude/skills/chrome-extension-author/templates"

mkdir -p "${EXT_DIR}"/{content-scripts,images,native,scripts}

# Always
cp "${TPL_DIR}/manifest.json.template"      "${EXT_DIR}/manifest.json"
cp "${TPL_DIR}/service_worker.js.template"  "${EXT_DIR}/service_worker.js"
cp "${TPL_DIR}/validate.sh.template"        "${EXT_DIR}/scripts/validate.sh"
chmod +x "${EXT_DIR}/scripts/validate.sh"
cp "${TPL_DIR}/icon-${ICON_STYLE}.svg.template" "${EXT_DIR}/images/icon.svg"

# Conditional (per Plan)
[ "$HAS_CONTENT_SCRIPT" = yes ] && cp "${TPL_DIR}/content-script.js.template" "${EXT_DIR}/content-scripts/main.js"
[ "$HAS_CURSOR" = yes ]         && cp "${TPL_DIR}/cursor.js.template"          "${EXT_DIR}/content-scripts/cursor.js"
[ "$HAS_POPUP" = yes ]          && cp "${TPL_DIR}/popup.html.template"         "${EXT_DIR}/popup.html" && \
                                   cp "${TPL_DIR}/popup.js.template"           "${EXT_DIR}/popup.js"
[ "$HAS_NATIVE" = yes ]         && cp "${TPL_DIR}/native-host.py.template"     "${EXT_DIR}/native/host.py" && \
                                   cp "${TPL_DIR}/native-host.json.template"   "${EXT_DIR}/native/host.json"

# Generate the 16/32/48/128 PNG pack from the SVG (see icon-design.md)
for SIZE in 16 32 48 128; do
  rsvg-convert -w $SIZE -h $SIZE "${EXT_DIR}/images/icon.svg" -o "${EXT_DIR}/images/icon${SIZE}.png"
done
```

Then `Edit` each scaffolded file to substitute the answer-derived values (`name`, `description`, `permissions`, `host_permissions`, `content_scripts.matches`, etc.). Every `REPLACE` placeholder must be resolved before scaffold is "done."

The generated extension also gets its own `agent-handbook.md` — a slim 1-page handoff explaining which architecture choices were made and which patterns from hermes-chrome are encoded. This is the breadcrumb future agents follow.

## 4. Verify

```bash
${EXT_DIR}/scripts/validate.sh
```

The validate wrapper checks:
- `manifest.json` parses as JSON
- `manifest_version: 3`
- Every file referenced in `manifest.json` exists: `background.service_worker`, `content_scripts[].js`, `web_accessible_resources[].resources`, `action.default_popup`, `icons.*`
- All PNG icon sizes present
- No `console.error` left in templates outside legitimate error paths (greps for the pattern)
- If native messaging in plan: `native/host.json` parses and points to `host.py`

Must exit 0. If hard finding, **fix the generated file**, not the template; the operator's extension takes precedence over a one-off scaffold quirk.

## 5. Print install + test instructions

End the run with a block the operator can act on immediately:

```
✅ Scaffolded extensions/<name>/

Install (Chrome):
  1. Open chrome://extensions/
  2. Toggle "Developer mode" (top right)
  3. Click "Load unpacked"
  4. Select: <absolute path to extensions/<name>/>
     (WSL2: \\wsl$\<distro>\<rest of path>)

Verify install:
  • The extension's icon appears in the toolbar
  • chrome://extensions/?errors=<extension-id> shows zero errors
  • Click the icon — popup appears (if popup chosen)
  • Navigate to any page — content scripts run (if content-script chosen)

Architecture choices recorded in: extensions/<name>/agent-handbook.md
Patterns encoded from hermes-chrome:
  <list of which patterns apply based on answers>
```

---

## Audience-specific flows

A generated extension is operated by both:

- **Operator** — clicks the toolbar icon, sees the overlay/badge/toast, uses the popup.
- **Agent** — drives the extension via the service worker's message contract or native messaging host.

The scaffolded `agent-handbook.md` inside the new extension documents both audiences for whoever inherits it.

### Operator flow (in the generated extension)

Whatever the operator does — click icon, navigate, toggle popup — the at-rest position of every visible indicator must be informative. Don't park cursors at edges, don't auto-hide badges within seconds.

### Agent-driven flow (in the generated extension)

If the extension's service worker exposes a message API (e.g. via native messaging host), the scaffolded handler templates already encode the discipline:
1. Idempotent message handlers — same message id may arrive twice after SW idle restart.
2. Re-check content-script injection state before sending into the page (`ensureContentScript(tabId)` pattern from hermes-chrome).
3. Debounce chatty event sources (`fs.watch`, `chrome.tabs.onUpdated`) before broadcasting.

---

## Script / command inventory

| Script / command | Purpose |
|---|---|
| `extensions/<name>/scripts/validate.sh` | Self-validate the generated extension (manifest schema, file existence, MV3 conformance) |
| `extensions/<name>/native/install.sh` *(if native messaging)* | Install the native messaging host manifest into the correct Chrome path for the OS |
| `rsvg-convert` (or `inkscape`, `magick`) | Generate 16/32/48/128 PNGs from `images/icon.svg` |
| `chrome://extensions/` | Manual install + Errors page check |

## Closeout — CLOSEOUT (mandatory)

- `scripts/validate.sh` on the generated extension must exit 0.
- Print install + test instructions as above.
- If the operator is on WSL2, also print the UNC path form.
- Suggest follow-ups (hot-reload tooling, native host install script, hermes-chrome bridge integration) as appropriate to the architecture chosen.
