# CSP and injection — isolated world, main world, web_accessible_resources

MV3 enforces a strict Content Security Policy for the extension's own pages AND for content scripts. Two layers of confusion meet here. The patterns below are the hermes-chrome learnings.

## Two worlds

When a content script runs in a tab, it can run in one of two JS contexts:

| World | What it sees | Can it interact with page JS? |
|---|---|---|
| **Isolated** (default) | Page DOM. Its own JS globals (not the page's). Its own listeners on `window`/`document`. | No. Page's `window.foo` is invisible. |
| **Main** (`world: "MAIN"` in `content_scripts` config) | Page DOM + page's JS globals + the page's CSP. | Yes — same context as the page's own scripts. |

Isolated world is the default and safer. Main world is necessary when the content script must:
- Hook into the page's app state (`window.__APP_STATE__`)
- Run inside the page's CSP (e.g., to load a font the page allows)
- Expose globals readable by the page (`window.myExtensionAPI`)

## The MV3 CSP trap

The isolated world's CSP **forbids inline `<script>` injected by the content script**. This bites every author once:

```js
// FAILS — isolated world CSP rejects inline JS
const s = document.createElement("script");
s.textContent = "alert('hi')";
document.head.appendChild(s);
```

The error is silent (just a CSP violation in the console). The script never runs.

## The fix — `web_accessible_resources`

Serve your runtime JS as a file the extension exposes, then inject a `<script src=>`:

1. **Declare the file in `manifest.json`:**

   ```json
   "web_accessible_resources": [{
     "resources": ["runtime.js", "images/*.svg"],
     "matches": ["<all_urls>"]
   }]
   ```

2. **Inject via `chrome.runtime.getURL`:**

   ```js
   const s = document.createElement("script");
   s.src = chrome.runtime.getURL("runtime.js");
   document.head.appendChild(s);
   ```

3. **The injected script runs in the MAIN world.** It can see and modify `window`, page globals, etc. — useful when the content script is bridging to page JS.

## Decision tree

| You need to | Use |
|---|---|
| Read/modify page DOM, no page-JS interaction | Isolated content script (default) |
| Read page's `window.__STATE__` or call page functions | Main-world content script (`world: "MAIN"`) OR isolated CS + injected `<script src>` |
| Stream a runtime JS file the operator can inspect / browser can cache | `web_accessible_resources` + injected `<script src>` |
| Load an SVG / image / font from the extension into a page | `web_accessible_resources` + `chrome.runtime.getURL(...)` |
| Make the extension expose a global API to the page | Main-world OR injected `<script>` from isolated |

## Cursor / overlay-runtime example (from hermes-chrome)

The hermes-chrome cursor is injected via main-world `<script src>` to keep state on `window.__af*` accessible to:
- The widget's runtime (also main-world)
- Bridge `evaluate` calls (which run in main world via DevTools Protocol)

If the cursor were in isolated world, `window.__afLastSseMessage` would only be visible from cursor.js itself, and the bridge couldn't read it for diagnostics.

That's why the scaffolded `cursor.js` template lives behind a `<script src=chrome-extension://.../cursor.js>` injection from a tiny bootstrap content script. Don't try to "simplify" by collapsing it back to a single isolated CS — you lose cross-world visibility.

## Common errors and what they mean

| Error | Cause |
|---|---|
| `Refused to execute inline script` | You injected an inline `<script>` from the isolated content script. Use `web_accessible_resources` + `<script src>`. |
| `Refused to load the script <ext-id>/runtime.js` | The file isn't in `web_accessible_resources` for the current page's URL pattern. Add or widen the `matches`. |
| `chrome.runtime is undefined` (inside the page) | You're inside a main-world script. `chrome.runtime` is only available in content-script context. Pass extension data via `postMessage` or DOM attributes. |
| `Manifest is missing or unreadable` | `web_accessible_resources` entry malformed (must be array of objects with `resources` + `matches`, not a flat array of strings — that's MV2). |

## Anti-patterns

- **`eval()` in the extension** — flagged by Chrome Web Store, broken under MV3 CSP. Don't.
- **Loading remote scripts via `<script src=https://...>` injection** — MV3 forbids remote code execution. All scripts must be bundled.
- **`Function("...")` as a code-string evaluator** — same as `eval()`.
- **Mixing isolated and main world in one file** — confusing; separate them. Bootstrap (isolated) injects runtime (main).
