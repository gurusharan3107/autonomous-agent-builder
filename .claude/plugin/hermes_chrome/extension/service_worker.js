const HOST_NAME = "com.hermes.chrome_bridge";
let port = null;
const attachedTabs = new Set();
const injectedTabs = new Set();
const sessionGroups = new Map(); // sessionName → groupId

function connectHost() {
  try {
    port = chrome.runtime.connectNative(HOST_NAME);
    port.onMessage.addListener((message) => {
      handleHostMessage(message).catch((error) => {
        post({ id: message?.id, success: false, error: String(error?.message || error) });
      });
    });
    port.onDisconnect.addListener(() => {
      port = null;
      setTimeout(connectHost, 2000);
    });
  } catch {
    port = null;
    setTimeout(connectHost, 5000);
  }
}

function post(message) {
  if (port) {
    try {
      port.postMessage(message);
    } catch (e) {
      console.error("postMessage failed:", e);
    }
  }
}

// Groups all tabs created during a named session under one Chrome tab group.
// Non-fatal: if tabGroups API is unavailable or the call fails, we skip silently.
async function ensureSessionGroup(sessionName, tabId) {
  let groupId = sessionGroups.get(sessionName);
  if (groupId !== undefined) {
    const valid = await chrome.tabGroups.get(groupId).catch(() => null);
    if (!valid) groupId = undefined;
  }
  if (groupId !== undefined) {
    await chrome.tabs.group({ tabIds: [tabId], groupId });
  } else {
    groupId = await chrome.tabs.group({ tabIds: [tabId] });
    await chrome.tabGroups.update(groupId, { title: sessionName, color: 'blue' });
    sessionGroups.set(sessionName, groupId);
  }
  return groupId;
}

function isControllableUrl(url) {
  return typeof url === "string" && /^(https?|file):\/\//i.test(url);
}

function unsupportedUrlReason(url) {
  if (!url) return "No tab URL is available";
  if (url.startsWith("file://")) {
    return "File URLs require Chrome extension file access to be enabled";
  }
  return `Chrome does not allow content-script injection on this URL: ${url}`;
}

async function currentTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    throw new Error("No active Chrome tab is available");
  }
  if (!isControllableUrl(tab.url)) {
    throw new Error(unsupportedUrlReason(tab.url));
  }
  return tab;
}

async function ensureAttached(tabId) {
  if (attachedTabs.has(tabId)) return;
  try {
    await withTimeout(chrome.debugger.attach({ tabId }, "1.3"), 3000, "debugger.attach");
  } catch (e) {
    // "Another debugger is already attached" means we lost the Set (service worker restarted)
    // but the debugger session is still live — treat as already attached.
    if (!String(e?.message || e).includes("already attached")) throw e;
  }
  attachedTabs.add(tabId);
  await withTimeout(chrome.debugger.sendCommand({ tabId }, "Runtime.enable"), 3000, "Runtime.enable");
  await withTimeout(chrome.debugger.sendCommand({ tabId }, "Page.enable"), 3000, "Page.enable");
}

async function send(tabId, method, params = {}) {
  await ensureAttached(tabId);
  return chrome.debugger.sendCommand({ tabId }, method, params);
}

async function evaluate(tabId, expression) {
  const result = await send(tabId, "Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true
  });
  if (result.exceptionDetails) {
    const detail = result.exceptionDetails.exception?.description || result.exceptionDetails.text;
    throw new Error(detail || "Runtime.evaluate failed");
  }
  return result.result?.value;
}

// Shared element-resolution helpers, injected into both resolvers' evaluate()
// expressions. Reject invisible/off-screen/occluded candidates (skip-links,
// 0×0 mobile-menu duplicates) so the cursor lands on what the operator expects.
const ELEMENT_RESOLVER_JS = `
  function __vis(el) {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 1 || r.height <= 1) return false;                       // 0×0 / 1px skip-links
    if (r.right <= 0 || r.left >= innerWidth) return false;                // horizontally off-screen (e.g. left:-9999 hide). Below/above the fold is allowed — __point scrollIntoViews.
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity || '1') === 0) return false;
    if (el.closest('[aria-hidden="true"]')) return false;
    return true;
  }
  function __point(el) {
    el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
    const r = el.getBoundingClientRect();
    const x = Math.round(r.left + r.width / 2), y = Math.round(r.top + r.height / 2);
    const top = document.elementFromPoint(x, y);                          // occlusion guard
    const onTarget = !!(top && (top === el || el.contains(top) || top.contains(el)));
    return { x, y, onTarget, tag: el.tagName,
             text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 160) };
  }
  function __pick(candidates) {
    // candidates: [{el, score}] — lower score = better match. Prefer better
    // score, then interactive tag, then smaller area, then DOM order. Return
    // the first whose click point is on-target; else the top-ranked point.
    const interactive = (e) => /^(A|BUTTON|SUMMARY|LABEL)$/.test(e.tagName) || e.getAttribute('role') === 'button';
    candidates.sort((a, b) => {
      if (a.score !== b.score) return a.score - b.score;
      const ai = interactive(a.el) ? 0 : 1, bi = interactive(b.el) ? 0 : 1;
      if (ai !== bi) return ai - bi;
      const ar = a.el.getBoundingClientRect(), br = b.el.getBoundingClientRect();
      return (ar.width * ar.height) - (br.width * br.height);
    });
    let first = null;
    for (const c of candidates) {
      const p = __point(c.el);
      if (!first) first = p;
      if (p.onTarget) return p;
    }
    return first;
  }
`;

async function findPointBySelector(tabId, selectorText) {
  const selector = JSON.stringify(String(selectorText || ""));
  const point = await evaluate(
    tabId,
    `(() => {
      ${ELEMENT_RESOLVER_JS}
      const els = Array.from(document.querySelectorAll(${selector})).filter(__vis);
      if (!els.length) return null;
      return __pick(els.map((el) => ({ el, score: 0 })));
    })()`
  );
  if (!point) throw new Error(`No visible element matched selector: ${selectorText}`);
  return point;
}

async function findPointByText(tabId, text) {
  const needle = JSON.stringify(String(text || ""));
  const point = await evaluate(
    tabId,
    `(() => {
      ${ELEMENT_RESOLVER_JS}
      const needle = ${needle}.toLowerCase().trim();
      if (!needle) return null;
      const els = Array.from(document.querySelectorAll(
        'a,button,[role=button],input[type=button],input[type=submit],label,summary,h1,h2,h3,h4,h5,h6,p,span,li,td,th'
      )).filter(__vis);
      const txt = (e) => (e.innerText || e.value || e.getAttribute('aria-label') || '').trim().toLowerCase();
      // score: 0 exact, 1 starts-with, 2 contains; skip non-matches.
      const candidates = [];
      for (const el of els) {
        const t = txt(el);
        if (!t.includes(needle)) continue;
        const score = t === needle ? 0 : (t.startsWith(needle) ? 1 : 2);
        candidates.push({ el, score });
      }
      if (!candidates.length) return null;
      return __pick(candidates);
    })()`
  );
  if (!point) throw new Error(`No visible clickable element matched text: ${text}`);
  return point;
}

async function moveCursorToPoint(tabId, point) {
  const response = await sendToContentScript(tabId, "moveToAndWait", [point.x, point.y, 900]);
  if (!response?.success) {
    throw new Error(response?.error || "Cursor movement failed");
  }
  return response.result || {};
}

async function clickAtPoint(tabId, point) {
  await moveCursorToPoint(tabId, point);
  const response = await sendToContentScript(tabId, "click", []);
  if (!response?.success) {
    throw new Error(response?.error || "Cursor click failed");
  }
}

// ---- Auto-inject content script on page load ----
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== 'complete') return;
  if (!tab.url || tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://') || tab.url.startsWith('chrome-search://')) return;
  if (injectedTabs.has(tabId)) return;
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ['content-scripts/cursor-agent.js']
    });
    injectedTabs.add(tabId);
  } catch {
    // Will retry on next interaction
  }
});

// ---- Content Script Injection Tracking ----
// (injectedTabs declared at top of file, line 4)

// Listen for content script ready pings and status queries
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg === 'hermes-cursor-ready' && sender.tab?.id) {
    injectedTabs.add(sender.tab.id);
  }
  if (msg && msg.type === 'hermes-cursor-status') {
    ensureContentScript(msg.tabId)
      .then((status) => sendResponse(status))
      .catch((error) => sendResponse({ injected: false, blocked: true, reason: String(error?.message || error) }));
    return true;
  }
});

// ---- Content Script Messaging ----
async function probeContentScript(tabId) {
  try {
    const response = await chrome.tabs.sendMessage(tabId, { action: "getStatus", args: [] });
    if (response?.success) {
      injectedTabs.add(tabId);
      return true;
    }
  } catch {
    return false;
  }
  return false;
}

async function ensureContentScript(tabId) {
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab?.id) {
    return { injected: false, blocked: true, reason: "Tab is no longer available" };
  }
  if (!isControllableUrl(tab.url)) {
    return { injected: false, blocked: true, reason: unsupportedUrlReason(tab.url), url: tab.url };
  }
  if (await probeContentScript(tabId)) {
    return { injected: true, url: tab.url };
  }
  try {
    // Clear the injection guard so a stale orphaned script (from a previous extension
    // reload) does not block re-initialization of the message listener.
    await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        document.documentElement.removeAttribute('data-hermes-agent-cursor-injected');
        window.__hermesAgentCursorInjected = false;
      }
    }).catch(() => {});
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ['content-scripts/cursor-agent.js']
    });
    await new Promise(r => setTimeout(r, 200));
  } catch (error) {
    return { injected: false, blocked: true, reason: String(error?.message || error), url: tab.url };
  }
  if (await probeContentScript(tabId)) {
    return { injected: true, url: tab.url };
  }
  return { injected: false, blocked: true, reason: "Content script did not respond after injection", url: tab.url };
}

function withTimeout(promise, ms, label) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms))
  ]);
}

async function sendToContentScript(tabId, action, args = []) {
  console.error(`sendToContentScript: starting ${action}`);
  const status = await withTimeout(
    ensureContentScript(tabId), 3000, `ensureContentScript(${action})`
  );
  console.error(`sendToContentScript: ensureContentScript done, injected=${status.injected}`);
  if (!status.injected) {
    throw new Error(status.reason || "Content script is not available");
  }
  const result = await withTimeout(
    chrome.tabs.sendMessage(tabId, { action, args }), 3000, `sendMessage(${action})`
  );
  console.error(`sendToContentScript: sendMessage done`);
  return result;
}

// ---- Browser Actions ----
async function runBrowserAction(action, state) {
  const type = action.type;
  console.error(`runBrowserAction: ${type}, tabId=${state.tabId}`);
  if (action.tabId) {
    state.tabId = action.tabId;
  }

  if (type === "goto") {
    let tab;
    if (state.tabId) {
      const current = await chrome.tabs.get(state.tabId);
      if (current.url === action.url && !action.reload) {
        tab = current;
      } else {
        tab = await chrome.tabs.update(state.tabId, { url: action.url, active: true });
      }
    } else {
      tab = await chrome.tabs.create({ url: action.url, active: true });
    }
    state.tabId = tab.id;
    state.lastUrl = tab.url || action.url;
    if (state.groupName) await ensureSessionGroup(state.groupName, state.tabId).catch(() => {});
    await new Promise((resolve) => setTimeout(resolve, action.waitMs || 2000));
    await ensureAttached(state.tabId).catch(() => {}); // pre-attach so screenshots never race
    return { type, tabId: state.tabId, url: tab.url || action.url };
  }

  if (!state.tabId) {
    const tab = await currentTab();
    state.tabId = tab.id;
  }

  if (type === "wait") {
    await new Promise((resolve) => setTimeout(resolve, action.ms || 1000));
    return { type, ms: action.ms || 1000 };
  }

  if (type === "wait_for_selector") {
    const selector = String(action.selector || "");
    const timeout = action.timeout || 5000;
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      try {
        const found = await evaluate(state.tabId, `!!document.querySelector(${JSON.stringify(selector)})`);
        if (found) return { type, selector };
      } catch { /* page still loading — retry */ }
      await new Promise(r => setTimeout(r, 250));
    }
    throw new Error(`wait_for_selector: "${selector}" not found after ${timeout}ms`);
  }

  if (type === "wait_for_url_change") {
    const timeout = action.timeout || 5000;
    const deadline = Date.now() + timeout;
    const anchor = await chrome.tabs.get(state.tabId).catch(() => null);
    if (!anchor) throw new Error("wait_for_url_change: tab not found");
    const fromUrl = action.from_url || anchor.url;
    while (Date.now() < deadline) {
      const current = await chrome.tabs.get(state.tabId).catch(() => null);
      if (!current) throw new Error("wait_for_url_change: tab was closed");
      if (current.url !== fromUrl && current.url !== "about:blank") {
        return { type, from: fromUrl, url: current.url };
      }
      await new Promise(r => setTimeout(r, 250));
    }
    throw new Error(`wait_for_url_change: URL still "${fromUrl}" after ${timeout}ms`);
  }

  if (type === "text") {
    const limit = action.maxChars || state.maxTextChars || 20000;
    const resp = await sendToContentScript(state.tabId, "getVisibleText", [limit]);
    const r = resp?.result;
    if (r && typeof r === 'object') return { type, url: r.url, title: r.title, text: r.text || '' };
    return { type, text: String(r || '') };
  }

  if (type === "snapshot") {
    const tab = await chrome.tabs.get(state.tabId).catch(() => null);
    const resp = await sendToContentScript(state.tabId, "getDOMSnapshot");
    const elements = resp?.result || [];
    return { type, url: tab?.url || '', title: tab?.title || '', element_count: elements.length, snapshot: elements };
  }

  if (type === "page_context") {
    const resp = await sendToContentScript(state.tabId, "getPageContext");
    return { type, ...(resp?.result || {}) };
  }

  if (type === "screenshot") {
    await ensureAttached(state.tabId);
    // Use JPEG by default — PNG easily exceeds Chrome's 1 MB native-messaging limit.
    const format = action.format === 'png' ? 'png' : 'jpeg';
    const params = { format, captureBeyondViewport: Boolean(action.full) };
    if (format === 'jpeg') params.quality = action.quality != null ? Number(action.quality) : 75;
    const capture = await chrome.debugger.sendCommand(
      { tabId: state.tabId },
      "Page.captureScreenshot",
      params
    );
    return { type, format, base64: capture.data };
  }

  if (type === "zoom") {
    await ensureAttached(state.tabId);
    const { x0 = 0, y0 = 0, x1, y1 } = action;
    if (x1 == null || y1 == null) throw new Error("zoom requires x0, y0, x1, y1");
    const quality = action.quality != null ? Number(action.quality) : 85;
    const capture = await chrome.debugger.sendCommand(
      { tabId: state.tabId },
      "Page.captureScreenshot",
      {
        format: 'jpeg',
        quality,
        clip: { x: Number(x0), y: Number(y0), width: Number(x1) - Number(x0), height: Number(y1) - Number(y0), scale: 1 },
        captureBeyondViewport: true,
      }
    );
    return { type, format: 'jpeg', x0, y0, x1, y1, base64: capture.data };
  }

  if (type === "close_tab") {
    const tab = await chrome.tabs.get(state.tabId).catch(() => null);
    if (tab?.url) state.lastUrl = tab.url;
    await chrome.tabs.remove(state.tabId);
    const closed = state.tabId;
    state.tabId = undefined;
    return { type, tabId: closed, url: state.lastUrl };
  }

  // ---- Cursor overlay actions (visible to user) ----
  if (type === "cursor_move") {
    const { x, y } = action;
    await sendToContentScript(state.tabId, "moveTo", [x, y]);
    return { type, x, y };
  }

  if (type === "cursor_click") {
    await sendToContentScript(state.tabId, "click", []);
    return { type };
  }

  if (type === "cursor_right_click") {
    await sendToContentScript(state.tabId, "rightClick", []);
    return { type };
  }

  if (type === "cursor_double_click") {
    await sendToContentScript(state.tabId, "dblClick", []);
    return { type };
  }

  if (type === "cursor_triple_click") {
    await sendToContentScript(state.tabId, "tripleClick", []);
    return { type };
  }

  if (type === "cursor_type") {
    const { text, append } = action;
    await sendToContentScript(state.tabId, "focusAndType", [text, { append: !!append }]);
    return { type, text };
  }

  if (type === "cursor_key") {
    const { key, modifiers } = action;
    await sendToContentScript(state.tabId, "keyPress", [key, modifiers || []]);
    return { type, key };
  }

  if (type === "cursor_drag") {
    const { x, y, duration } = action;
    await sendToContentScript(state.tabId, "dragTo", [x, y, duration || 500]);
    return { type, x, y };
  }

  if (type === "cursor_scroll") {
    const { deltaX, deltaY } = action;
    await sendToContentScript(state.tabId, "scroll", [deltaX || 0, deltaY || 0]);
    return { type, deltaX, deltaY };
  }

  if (type === "cursor_status") {
    const resp = await sendToContentScript(state.tabId, "getStatus");
    return { type, ...(resp?.result || {}) };
  }

  if (type === "cursor_hide") {
    await sendToContentScript(state.tabId, "hide", []);
    return { type };
  }

  // ---- Extension interaction actions ----
  if (type === "click_text") {
    const point = await findPointByText(state.tabId, action.text);
    await clickAtPoint(state.tabId, point);
    return { type, text: action.text, point };
  }

  if (type === "fill_selector") {
    const point = await findPointBySelector(state.tabId, action.selector);
    await clickAtPoint(state.tabId, point);
    const response = await sendToContentScript(state.tabId, "focusAndType", [
      String(action.value || ""),
      { append: Boolean(action.append) }
    ]);
    if (!response?.success) {
      throw new Error(response?.error || `Could not fill selector: ${action.selector}`);
    }
    return { type, selector: action.selector, point };
  }

  if (type === "click_selector") {
    const point = await findPointBySelector(state.tabId, action.selector);
    await clickAtPoint(state.tabId, point);
    return { type, selector: action.selector, point };
  }

  if (type === "evaluate") {
    const result = await evaluate(state.tabId, action.expression);
    return { type, result };
  }

  throw new Error(`Unsupported action type: ${type}`);
}

async function handleHostMessage(message) {
  const state = {
    maxTextChars: message.maxTextChars || 20000,
    tabId: message.useSelectedTab ? (await currentTab()).id : undefined,
    groupName: message.sessionName || null,
  };
  if (state.tabId && state.groupName) await ensureSessionGroup(state.groupName, state.tabId).catch(() => {});
  if (message?.type === "reload") {
    post({ id: message.id, success: true, message: "reloading" });
    setTimeout(() => chrome.runtime.reload(), 150);
    return;
  }

  if (message?.type === "status") {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const activeTab = tabs[0] || null;
    const contentScript = activeTab?.id
      ? await ensureContentScript(activeTab.id)
      : { injected: false, blocked: true, reason: "No active tab" };
    post({
      id: message.id,
      success: true,
      extension: "Hermes Chrome Bridge",
      active_tab: activeTab ? { id: activeTab.id, title: activeTab.title, url: activeTab.url } : null,
      content_script: contentScript
    });
    return;
  }
  if (message?.type !== "run") {
    throw new Error(`Unsupported host message type: ${message?.type}`);
  }
  const results = [];
  for (const action of message.actions || []) {
    const result = await runBrowserAction(action, state);
    if (result?.url) state.lastUrl = result.url;
    results.push(result);
  }
  const tab = state.tabId ? await chrome.tabs.get(state.tabId).catch(() => null) : null;
  post({ id: message.id, success: true, final_url: tab?.url || state.lastUrl, results });
}

connectHost();

// Keep-alive: MV3 service workers terminate after 30s idle.
// An alarm every ~25s resets the idle clock before it expires.
// Unpacked (dev-loaded) extensions have no minimum alarm interval.
chrome.alarms.create("hermes-keepalive", { periodInMinutes: 25 / 60 });
chrome.alarms.onAlarm.addListener((_alarm) => {
  // No-op — handling the event is sufficient to reset the idle timeout.
});
