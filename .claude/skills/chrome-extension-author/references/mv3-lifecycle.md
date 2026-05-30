# MV3 lifecycle — service worker, content scripts, re-injection

Chrome MV3 retired persistent background pages. The service worker idles after ~30 seconds of inactivity; the OS may wake it for events but no state survives the idle. Content scripts re-inject on every page navigation. Designing for this is non-optional.

## Service worker lifecycle

```
install/update ──► startup ──► (idle ≈ 30s no events) ──► sleep ──► (event arrives) ──► wake ──► ...
```

What that means for code:

1. **Globals reset on every wake.** Anything you assigned to `globalThis` or a module-level `let` is gone after idle. Persist with `chrome.storage.local` if needed.
2. **Timers don't survive.** `setTimeout` / `setInterval` are killed on idle. Use `chrome.alarms` for scheduled work — Chrome wakes the SW when the alarm fires.
3. **Connected ports drop.** `chrome.runtime.connectNative` ports break on idle. The SW's `port.onDisconnect` fires; the next message reconnects.
4. **Listeners must re-register on every wake.** Top-level `chrome.tabs.onUpdated.addListener(...)` calls re-run on every wake; that's fine. Don't conditionally register inside an async path that might not run.

### Keep-alive (use sparingly)

If a brief task spans multiple events and you must avoid idle mid-flow, send a self-message every 25s:

```js
chrome.alarms.create("keepalive", { periodInMinutes: 0.4 }); // ≈ 24s
chrome.alarms.onAlarm.addListener(a => { if (a.name === "keepalive") {/* nothing */} });
```

Don't use this as the default. It defeats the SW idle model and ages the browser process. Use only when you have a documented reason.

## Content script lifecycle

```
page navigation ──► (Chrome resets DOM) ──► matched content_script injected at run_at ──► IIFE runs ──► page interactions ──► (next navigation) ──► destroyed
```

What that means:

1. **No state survives navigation.** Each page is a fresh closure. Persist via `chrome.storage` (broadcasted to all CSes) or `localStorage` (page-scoped, see [`best-practices.md`](best-practices.md) for the safe-parse pattern).
2. **`document_start` vs `document_idle`** in the manifest: `document_start` runs before any page JS — needed for overlays that must beat the page's CSS. `document_idle` runs after page load — safer for DOM-reading content scripts.
3. **Re-injection on SPA navigation:** SPAs (React, Vue, etc.) don't fire `tabs.onUpdated complete` on route changes. If your CS must react to SPA navigation, use a `MutationObserver` on `<body>` or a `history.pushState` patch from inside the CS.
4. **`window` is the page's window** when the CS runs in "main world" (MV3 `world: "MAIN"`), and a separate isolated world otherwise. Reading/writing `window.__foo` only works cross-script if both are in the same world. See [`csp-and-injection.md`](csp-and-injection.md).

## The ensureContentScript pattern

When the SW must send a message to a content script that may not be injected yet:

```js
async function ensureContentScript(tabId) {
  if (injectedTabs.has(tabId)) return { injected: true };
  // Probe first — maybe a stale tab from before SW idle
  try {
    const ping = await chrome.tabs.sendMessage(tabId, { type: "ping" });
    if (ping?.ok) { injectedTabs.add(tabId); return { injected: true }; }
  } catch { /* CS not present */ }
  // Inject explicitly
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content-scripts/main.js"]
    });
    injectedTabs.add(tabId);
    return { injected: true };
  } catch (e) {
    return { injected: false, reason: String(e?.message || e) };
  }
}
```

Key points:
- `injectedTabs` is a `Set` that's wiped on SW idle. The probe-then-inject pattern handles both cold start and re-injection.
- Some URLs reject injection (`chrome://`, `about:`, `view-source:`). The catch handles them; return a sensible reason so the SW can surface "blocked URL" instead of crashing.

## Auto-injection on navigation

If the extension's content scripts should run on every matched page (overlays, monitors, agent-feedback widgets), register on `tabs.onUpdated`:

```js
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete") return;
  if (!tab.url || tab.url.startsWith("chrome://") || tab.url.startsWith("about:")) return;
  if (injectedTabs.has(tabId)) return;
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content-scripts/main.js"]
    });
    injectedTabs.add(tabId);
  } catch { /* will retry on next interaction */ }
});
```

The guard against `chrome://` / `about:` is non-optional. Without it, the SW logs an error on every browser-page navigation.

## Permission promises — return `true` from `onMessage`

The classic gotcha: `chrome.runtime.onMessage` callbacks that return without explicitly returning `true` after starting an async response leave the sender hanging forever.

```js
// WRONG — sendResponse never called from the caller's perspective
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  doAsync().then(sendResponse);
});

// RIGHT — explicit return true keeps the channel open
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  doAsync().then(sendResponse);
  return true;
});
```

The scaffolded service-worker template always returns `true` for async handlers. Don't remove that pattern.
