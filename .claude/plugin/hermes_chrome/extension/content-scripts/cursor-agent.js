/**
 * Hermes Chrome Bridge — Floating Cursor Agent Overlay
 * 
 * Renders a visible floating cursor on every page that shows where
 * the AI agent is interacting. The cursor:
 * - Is a non-interfering overlay (pointerEvents: none on base layer)
 * - Animates smoothly between positions
 * - Passes real clicks through to the underlying page at the cursor position
 */
(() => {
  // Prevent double-injection, but allow re-injection if the extension context was invalidated (e.g. after reload).
  if (document.documentElement.dataset.hermesAgentCursorInjected) {
    try {
      void chrome.runtime.id; // throws "Extension context invalidated" after a reload
      return;
    } catch {
      document.documentElement.removeAttribute('data-hermes-agent-cursor-injected');
    }
  }
  document.documentElement.dataset.hermesAgentCursorInjected = "true";
  window.__hermesAgentCursorInjected = true;

  // ---- State ----
  let cursorX = -100;
  let cursorY = -100;
  let cursorEl = null;
  let pointerEl = null;
  let animationFrame = null;
  let isVisible = false;
  let cursorPhase = 'idle'; // idle | moving | clicking | arrived

  const HERMES_CURSOR_ID = 'hermes-agent-cursor-overlay';
  const POINTER_SVG = chrome.runtime.getURL('images/pointer-shape-animated.svg') + '?v=codex-like-2';

  // ---- Styles ----
  const css = `
    #${HERMES_CURSOR_ID} {
      position: fixed;
      z-index: 2147483647;
      pointer-events: none;
      left: 0;
      top: 0;
      will-change: transform;
      transform: translate(-100px, -100px);
      /* Compositor-driven glide: animates even when Chrome is NOT the foreground
         window, unlike requestAnimationFrame (throttled to ~1fps in background). */
      transition: transform 0.32s cubic-bezier(0.22, 0.61, 0.36, 1), opacity 0.2s ease;
      opacity: 0;
    }
    #${HERMES_CURSOR_ID}.hermes-visible {
      opacity: 1;
    }
    #${HERMES_CURSOR_ID} .hermes-cursor-pointer {
      width: 18px;
      height: 18px;
      display: block;
      transform: translate(-1px, -1px);
      transform-origin: 1px 1px;
      filter:
        drop-shadow(0 0 8px rgba(73, 182, 255, 0.55))
        drop-shadow(0 2px 3px rgba(0,0,0,0.32));
      transition: transform 0.12s ease;
      animation: hermes-pointer-idle 1.7s ease-in-out infinite;
      user-select: none;
      -webkit-user-drag: none;
    }
    #${HERMES_CURSOR_ID}.hermes-moving .hermes-cursor-pointer {
      animation: hermes-pointer-moving 0.48s ease-in-out infinite;
    }
    #${HERMES_CURSOR_ID} .hermes-cursor-pointer.hermes-clicking {
      transform: translate(-1px, -1px) scale(0.86);
      animation: none;
    }
    @keyframes hermes-pointer-idle {
      0%, 100% { transform: translate(-1px, -1px) rotate(0deg); }
      50% { transform: translate(0, -2px) rotate(0.35deg); }
    }
    @keyframes hermes-pointer-moving {
      0%, 100% { transform: translate(-1px, -1px) rotate(-2deg); }
      50% { transform: translate(1px, -3px) rotate(2deg); }
    }
  `;

  // ---- DOM Setup ----
  function createOverlay() {
    // Remove stale
    const old = document.getElementById(HERMES_CURSOR_ID);
    if (old) old.remove();

    const style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    cursorEl = document.createElement('div');
    cursorEl.id = HERMES_CURSOR_ID;

    const pointerImg = document.createElement('img');
    pointerImg.className = 'hermes-cursor-pointer';
    pointerImg.src = POINTER_SVG;
    pointerImg.alt = '';
    pointerImg.decoding = 'async';
    pointerEl = pointerImg;

    cursorEl.appendChild(pointerImg);
    document.documentElement.appendChild(cursorEl);

    isVisible = false;
  }

  // ---- Motion ----
  // RELIABILITY CONTRACT: the *logical* position (cursorX/cursorY) snaps to the
  // target immediately, so click() / elementFromPoint always resolve the element
  // the operator asked for — even if the visible glide hasn't finished or the
  // tab is backgrounded. The *visible* glide is a CSS transform transition
  // (compositor-driven), so the operator still sees the cursor travel to the
  // target. What is seen and what is clicked therefore always agree.
  const GLIDE_MS = 320;
  let arrivalTimer = null;

  function moveTo(x, y) {
    if (!cursorEl) createOverlay();
    cursorX = x;
    cursorY = y;
    if (!isVisible) {
      cursorEl.classList.add('hermes-visible');
      isVisible = true;
    }
    cursorPhase = 'moving';
    cursorEl.classList.add('hermes-moving');
    cursorEl.style.transform = `translate(${x}px, ${y}px)`; // CSS transition glides
    if (arrivalTimer) clearTimeout(arrivalTimer);
    arrivalTimer = setTimeout(() => {
      cursorPhase = 'idle';
      cursorEl?.classList.remove('hermes-moving');
    }, GLIDE_MS);
  }

  function moveToAndWait(x, y, timeoutMs = 900) {
    moveTo(x, y);
    // Logical position is already at the target; wait only for the visible glide
    // so the operator sees the cursor arrive before the click. setTimeout (not
    // rAF) resolves promptly even in a backgrounded tab.
    const wait = Math.min(GLIDE_MS + 40, Math.max(0, timeoutMs));
    return new Promise((resolve) => setTimeout(() => resolve(getStatus()), wait));
  }

  function click() {
    if (!cursorEl) return;
    pointerEl?.classList.add('hermes-clicking');
    setTimeout(() => pointerEl?.classList.remove('hermes-clicking'), 140);

    // Hide cursor momentarily so elementFromPoint gets the real page element
    const wasVisible = isVisible;
    if (wasVisible) cursorEl.classList.remove('hermes-visible');
    const el = document.elementFromPoint(cursorX, cursorY);
    if (wasVisible) cursorEl.classList.add('hermes-visible');

    if (el) {
      const scrollX = window.scrollX || 0;
      const scrollY = window.scrollY || 0;
      const opts = { bubbles: true, cancelable: true, view: window };
      el.dispatchEvent(new MouseEvent('mousedown', { ...opts, clientX: cursorX, clientY: cursorY, pageX: cursorX + scrollX, pageY: cursorY + scrollY }));
      el.dispatchEvent(new MouseEvent('mouseup', { ...opts, clientX: cursorX, clientY: cursorY, pageX: cursorX + scrollX, pageY: cursorY + scrollY }));
      el.dispatchEvent(new MouseEvent('click', { ...opts, clientX: cursorX, clientY: cursorY, pageX: cursorX + scrollX, pageY: cursorY + scrollY }));
    }
    flashLabel('click');
  }

  function tripleClick() {
    if (!cursorEl) return;
    const wasVisible = isVisible;
    if (wasVisible) cursorEl.classList.remove('hermes-visible');
    const el = document.elementFromPoint(cursorX, cursorY);
    if (wasVisible) cursorEl.classList.add('hermes-visible');
    if (el) {
      const opts = { bubbles: true, cancelable: true, view: window };
      [1, 2, 3].forEach(() => {
        el.dispatchEvent(new MouseEvent('mousedown', { ...opts, clientX: cursorX, clientY: cursorY }));
        el.dispatchEvent(new MouseEvent('mouseup', { ...opts, clientX: cursorX, clientY: cursorY }));
        el.dispatchEvent(new MouseEvent('click', { ...opts, clientX: cursorX, clientY: cursorY }));
      });
    }
    flashLabel('triple-click');
  }

  function rightClick() {
    if (!cursorEl) return;
    const wasVisible = isVisible;
    if (wasVisible) cursorEl.classList.remove('hermes-visible');
    const el = document.elementFromPoint(cursorX, cursorY);
    if (wasVisible) cursorEl.classList.add('hermes-visible');
    if (el) {
      el.dispatchEvent(new MouseEvent('contextmenu', {
        bubbles: true, cancelable: true, view: window,
        clientX: cursorX, clientY: cursorY
      }));
    }
    flashLabel('right-click');
  }

  function dblClick() {
    if (!cursorEl) return;
    const wasVisible = isVisible;
    if (wasVisible) cursorEl.classList.remove('hermes-visible');
    const el = document.elementFromPoint(cursorX, cursorY);
    if (wasVisible) cursorEl.classList.add('hermes-visible');
    if (el) {
      const opts = { bubbles: true, cancelable: true, view: window };
      el.dispatchEvent(new MouseEvent('mousedown', { ...opts, clientX: cursorX, clientY: cursorY }));
      el.dispatchEvent(new MouseEvent('mouseup', { ...opts, clientX: cursorX, clientY: cursorY }));
      el.dispatchEvent(new MouseEvent('dblclick', { ...opts, clientX: cursorX, clientY: cursorY }));
    }
    flashLabel('double-click');
  }

  function focusAndType(text, opts = {}) {
    if (!cursorEl) return;
    const wasVisible = isVisible;
    if (wasVisible) cursorEl.classList.remove('hermes-visible');
    const el = document.elementFromPoint(cursorX, cursorY);
    if (wasVisible) cursorEl.classList.add('hermes-visible');
    if (!el) return;
    el.focus();
    if (opts.append && el.value !== undefined) {
      // Insert text at cursor / append
      const start = el.selectionStart || el.value.length;
      const end = el.selectionEnd || el.value.length;
      el.value = el.value.slice(0, start) + text + el.value.slice(end);
      el.selectionStart = el.selectionEnd = start + text.length;
    } else if (el.value !== undefined) {
      el.value = text;
    } else if ('innerText' in el) {
      el.innerText = text;
    }
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    flashLabel('type');
  }

  function keyPress(key, modifiers = []) {
    if (!cursorEl) return;
    const wasVisible = isVisible;
    if (wasVisible) cursorEl.classList.remove('hermes-visible');
    const el = document.elementFromPoint(cursorX, cursorY) || document.activeElement || document.body;
    if (wasVisible) cursorEl.classList.add('hermes-visible');
    const opts = {
      bubbles: true, cancelable: true, view: window,
      key, code: key,
      ctrlKey: modifiers.includes('control') || modifiers.includes('ctrl'),
      shiftKey: modifiers.includes('shift'),
      altKey: modifiers.includes('alt') || modifiers.includes('option'),
      metaKey: modifiers.includes('command') || modifiers.includes('cmd'),
    };
    el.dispatchEvent(new KeyboardEvent('keydown', opts));
    el.dispatchEvent(new KeyboardEvent('keypress', opts));
    el.dispatchEvent(new KeyboardEvent('keyup', opts));
    flashLabel(`⌨ ${key}`);
  }

  function dragTo(endX, endY, duration = 500) {
    return new Promise((resolve) => {
      const startX = cursorX;
      const startY = cursorY;
      const startTime = performance.now();
      const wasVisible = isVisible;
      if (wasVisible) cursorEl.classList.remove('hermes-visible');
      const el = document.elementFromPoint(cursorX, cursorY);
      if (wasVisible) cursorEl.classList.add('hermes-visible');
      if (el) {
        el.dispatchEvent(new MouseEvent('mousedown', {
          bubbles: true, cancelable: true, view: window,
          clientX: cursorX, clientY: cursorY
        }));
      }
      function step(now) {
        const t = Math.min(1, (now - startTime) / duration);
        const x = startX + (endX - startX) * t;
        const y = startY + (endY - startY) * t;
        moveTo(x, y);
        if (el) {
          el.dispatchEvent(new MouseEvent('mousemove', {
            bubbles: true, cancelable: true, view: window,
            clientX: x, clientY: y
          }));
        }
        if (t < 1) {
          requestAnimationFrame(step);
        } else {
          if (el) {
            el.dispatchEvent(new MouseEvent('mouseup', {
              bubbles: true, cancelable: true, view: window,
              clientX: endX, clientY: endY
            }));
          }
          flashLabel('drag');
          resolve();
        }
      }
      requestAnimationFrame(step);
    });
  }

  function scroll(deltaX, deltaY) {
    const el = document.elementFromPoint(cursorX, cursorY) || document.documentElement;
    el.scrollBy(deltaX, deltaY);
    const we = new WheelEvent('wheel', {
      bubbles: true, cancelable: true, view: window,
      clientX: cursorX, clientY: cursorY,
      deltaX, deltaY
    });
    el.dispatchEvent(we);
    flashLabel('scroll');
  }

  function getVisibleText(maxChars) {
    return {
      url: location.href,
      title: document.title,
      text: (document.body?.innerText || '').trim().slice(0, maxChars)
    };
  }

  function _isVisible(el) {
    try {
      const s = window.getComputedStyle(el);
      if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    } catch { return true; }
  }

  function getDOMSnapshot() {
    // Excludes div/span containers — they duplicate all descendant text via innerText.
    // Focuses on interactive + semantic elements only.
    const SELECTOR = 'a,button,input,textarea,select,[role],h1,h2,h3,h4,h5,h6,label,p,li,td,th';
    return Array.from(document.querySelectorAll(SELECTOR))
      .filter(_isVisible)
      .filter(el => {
        const t = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
        return t.length > 0 || el.href || el.getAttribute('role');
      })
      .slice(0, 200)
      .map((el, i) => {
        const entry = {
          i,
          tag: el.tagName,
          role: el.getAttribute('role') || '',
          text: (el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 120),
          href: el.href || ''
        };
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') {
          entry.value = String(el.value || '').slice(0, 100);
          entry.input_type = el.type || '';
          entry.name = el.name || el.id || '';
        }
        return entry;
      });
  }

  function getPageContext() {
    // Lightweight overview — use before snapshot for progressive disclosure.
    function vis(el) { return _isVisible(el); }
    return {
      url: location.href,
      title: document.title,
      headings: Array.from(document.querySelectorAll('h1,h2,h3')).filter(vis)
        .map(h => ({ tag: h.tagName, text: h.innerText?.trim().slice(0, 100) })).filter(h => h.text).slice(0, 8),
      nav: Array.from(document.querySelectorAll('nav a,[role="navigation"] a,[role="menubar"] *,[role="tablist"] *'))
        .filter(vis).map(a => ({ text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 60), href: a.href || '' }))
        .filter(x => x.text).slice(0, 20),
      buttons: Array.from(document.querySelectorAll('button,[role="button"]')).filter(vis)
        .map(b => (b.innerText || b.getAttribute('aria-label') || '').trim().slice(0, 60)).filter(Boolean).slice(0, 15),
      inputs: Array.from(document.querySelectorAll('input,textarea,select')).filter(vis)
        .map(el => ({ name: el.name || el.id || el.placeholder || '', type: el.type || el.tagName.toLowerCase(), value: String(el.value || '').slice(0, 60) }))
        .filter(x => x.name).slice(0, 10)
    };
  }

  function flashLabel(label) {
    return label;
  }

  function getStatus() {
    return {
      visible: isVisible,
      x: Math.round(cursorX),
      y: Math.round(cursorY),
      phase: cursorPhase,
      url: location.href,
      title: document.title
    };
  }

  function hide() {
    if (cursorEl) cursorEl.classList.remove('hermes-visible');
    if (cursorEl) cursorEl.classList.remove('hermes-moving');
    isVisible = false;
    cursorPhase = 'idle';
  }

  function destroy() {
    if (animationFrame) cancelAnimationFrame(animationFrame);
    const old = document.getElementById(HERMES_CURSOR_ID);
    if (old) old.remove();
    window.__hermesAgentCursorInjected = false;
  }

  // ---- Message Listener (from service worker) ----
  const actions = {
    moveTo, moveToAndWait, click, tripleClick, rightClick, dblClick,
    focusAndType, keyPress, dragTo, scroll,
    getVisibleText, getDOMSnapshot, getPageContext,
    getStatus, hide, destroy
  };

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    const fn = actions[msg.action];
    if (!fn) {
      sendResponse({ success: false, error: `Unknown action: ${msg.action}` });
      return true;
    }
    try {
      const result = fn(...(msg.args || []));
      if (result instanceof Promise) {
        result.then(r => sendResponse({ success: true, result: r }))
              .catch(e => sendResponse({ success: false, error: String(e) }));
        return true;
      }
      sendResponse({ success: true, result });
    } catch (err) {
      sendResponse({ success: false, error: String(err) });
    }
    return true;
  });

  // ---- Init ----
  createOverlay();

  // Notify service worker that content script is ready
  try { chrome.runtime.sendMessage('hermes-cursor-ready'); } catch {}
})();
