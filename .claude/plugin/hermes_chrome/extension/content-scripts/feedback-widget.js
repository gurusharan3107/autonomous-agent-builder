/**
 * Hermes Chrome Bridge — Feedback Widget content script.
 *
 * Injected on-demand by service_worker.js when the popup toggle is flipped on.
 *
 * Loads overlay.html (markup + styles) from the extension, strips its inline
 * <script>, mounts the markup into the page, then loads the IIFE via a separate
 * <script src=chrome-extension://.../feedback-widget-runtime.js>. The script-via-src
 * path is mandatory: MV3's isolated-world CSP blocks any inline <script> a content
 * script tries to inject into the page (`script-src 'self' 'wasm-unsafe-eval'
 * 'inline-speculation-rules' chrome-extension://<id>/`). Scripts served from the
 * extension URL are allowed because the extension's own URL is in that CSP.
 *
 * Queue origin (e.g. http://127.0.0.1:4177) is passed via data-queue-origin on the
 * mount node; the runtime reads it from there and uses it as the fetch base.
 */
(() => {
  const FLAG = "__hermesFeedbackWidgetInjected";
  if (window[FLAG]) return;
  window[FLAG] = true;

  // Use `localhost`, NOT `127.0.0.1`. WSL2 Node bound to IPv6 wildcard (::) is reachable
  // from Windows-side Chrome via `localhost` (→ [::1]) but NOT via `127.0.0.1` (IPv4
  // forwarding bridge for Node's IPv6 socket fails). The artifact-feedback-server
  // could be bound to 0.0.0.0 to fix this at the server side, but using `localhost`
  // here works for both WSL and macOS without any server change.
  const QUEUE_ORIGIN =
    (window.__HERMES_FEEDBACK_QUEUE_ORIGIN) || "http://localhost:4177";

  (async () => {
    let html;
    try {
      const url = chrome.runtime.getURL("content-scripts/overlay.html");
      const res = await fetch(url);
      if (!res.ok) throw new Error(`overlay fetch ${res.status}`);
      html = await res.text();
    } catch (err) {
      console.error("[hermes-feedback] failed to load overlay.html:", err);
      window[FLAG] = false;
      return;
    }

    const container = document.createElement("div");
    container.id = "hermes-feedback-mount";
    container.dataset.queueOrigin = QUEUE_ORIGIN;
    container.innerHTML = html;

    // Strip inline <script> blocks — they will not execute under MV3 isolated-world
    // CSP. The runtime is loaded separately via <script src>.
    container.querySelectorAll("script").forEach((s) => s.remove());

    document.body.appendChild(container);

    const runtime = document.createElement("script");
    runtime.src = chrome.runtime.getURL("content-scripts/feedback-widget-runtime.js");
    runtime.async = false;
    runtime.onerror = (e) => console.error("[hermes-feedback] runtime load error", e);
    document.body.appendChild(runtime);

    console.log("[hermes-feedback] widget mounted; queue origin:", QUEUE_ORIGIN);
  })();
})();
