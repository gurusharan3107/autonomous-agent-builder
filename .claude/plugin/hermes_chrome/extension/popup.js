document.addEventListener('DOMContentLoaded', async () => {
  const $ = id => document.getElementById(id);
  const dot = $('dot');
  const sub = $('sub');
  const err = $('err');

  function sv(el, state, text) { el.textContent = text; el.className = 'val ' + state; }
  function sd(s) { dot.className = 'dot ' + (s === 'ok' ? 'ok' : s === 'bad' ? 'bad' : 'warn'); }
  function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

  $('ext-id').textContent = chrome.runtime.id || '—';
  $('sock').textContent = '~/.hermes/run/chrome-bridge.sock';

  // ---- Queue origin (cross-origin mode) ----
  // Blank = same-origin (the page being annotated is served by the feedback server).
  // Set to e.g. http://localhost:7878 when annotating a SEPARATE running app whose
  // feedback queue server lives on another origin. Persisted globally and injected
  // by the service worker before the widget loads.
  const originInput = $('queue-origin');
  const hintRow = $('queue-origin-hint-row');
  const hintOut = $('queue-origin-hint');
  if (originInput) {
    const showHint = (msg, bad) => {
      hintOut.textContent = msg || '';
      hintOut.style.color = bad ? '#f87171' : '#52525b';
      hintRow.style.display = msg ? 'flex' : 'none';
    };
    const { feedbackQueueOrigin } = await chrome.storage.local.get('feedbackQueueOrigin');
    if (feedbackQueueOrigin) originInput.value = feedbackQueueOrigin;
    const save = async () => {
      const raw = originInput.value.trim().replace(/\/$/, '');
      if (!raw) {
        await chrome.storage.local.remove('feedbackQueueOrigin');
        showHint('Same-origin — posts to the annotated page’s own server.');
        return;
      }
      let ok = false;
      try { const u = new URL(raw); ok = /^https?:$/.test(u.protocol) && u.origin === raw; } catch { ok = false; }
      if (!ok) {
        showHint('Must be a bare origin, e.g. http://localhost:7878', true);
        return;
      }
      await chrome.storage.local.set({ feedbackQueueOrigin: raw });
      showHint('Saved — re-toggle Feedback Mode to apply.');
    };
    originInput.addEventListener('change', save);
    originInput.addEventListener('blur', save);
  }

  // Extension is loaded (popup is running)
  sv($('ext-status'), 'ok', 'Loaded ✓');
  sd('ok');
  sub.textContent = 'Connected — OWL is ready';

  // Find the actual active tab. Hermes should not silently switch tabs.
  let tab = null;
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    tab = tabs[0] || null;
  } catch (e) {
    err.textContent = 'Tab query failed: ' + e.message;
    err.classList.add('show');
  }

  if (tab) {
    const url = tab.url ? tab.url.replace(/^https?:\/\//, '').replace(/\/$/, '').substring(0, 48) : '';
    $('tab').innerHTML = `<div class="card"><div class="card-title">${esc(tab.title || 'Untitled')}</div><div class="card-url">${esc(url)}</div></div>`;

    if (/^(https?|file):\/\//i.test(tab.url || '')) {
      try {
        const swResponse = await chrome.runtime.sendMessage({ type: 'hermes-cursor-status', tabId: tab.id });
        if (swResponse?.injected) {
          sv($('cs-status'), 'ok', 'Injected ✓');
        } else {
          sv($('cs-status'), swResponse?.blocked ? 'bad' : 'warn', swResponse?.reason || 'Not injected');
        }
      } catch (e) {
        sv($('cs-status'), 'bad', 'Check failed');
        err.textContent = 'Content script check failed: ' + e.message;
        err.classList.add('show');
      }
    } else {
      sv($('cs-status'), 'warn', 'Blocked on this URL');
    }

    // ---- Feedback Mode toggle ----
    const toggle = $('feedback-toggle');
    const errRow = $('feedback-err-row');
    const errOut = $('feedback-err');
    const storageKey = `feedback-mode:${tab.id}`;

    const showErr = (msg) => {
      errOut.textContent = msg || '';
      errRow.style.display = msg ? 'flex' : 'none';
    };
    const paint = (on) => {
      toggle.classList.toggle('on', !!on);
      toggle.setAttribute('aria-checked', on ? 'true' : 'false');
    };

    const { [storageKey]: stored } = await chrome.storage.local.get(storageKey);
    paint(!!stored);

    const handle = async () => {
      if (toggle.classList.contains('busy')) return;
      const next = !toggle.classList.contains('on');
      toggle.classList.add('busy');
      showErr('');
      try {
        const result = await chrome.runtime.sendMessage({
          type: 'hermes-feedback-toggle',
          tabId: tab.id,
          enabled: next
        });
        if (result?.ok) {
          paint(next);
          await chrome.storage.local.set({ [storageKey]: next });
        } else {
          showErr(result?.error || 'Toggle failed');
        }
      } catch (e) {
        showErr(e.message || String(e));
      } finally {
        toggle.classList.remove('busy');
      }
    };
    toggle.addEventListener('click', handle);
    toggle.addEventListener('keydown', (e) => {
      if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); handle(); }
    });
  } else {
    $('tab').innerHTML = '<div class="empty">No active tab detected</div>';
    sv($('cs-status'), 'warn', 'No tab');
  }
});
