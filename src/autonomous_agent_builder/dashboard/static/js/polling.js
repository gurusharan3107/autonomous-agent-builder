/**
 * HTMX polling enhancements — feedback, error handling, re-animation.
 */
(function () {
  // ── Re-animate new cards after HTMX swap ──
  document.addEventListener('htmx:afterSwap', function (e) {
    if (!window.animateCardsEntrance) return;
    if (typeof gsap === 'undefined') return;

    var target = e.detail.target;
    var newCards = target.querySelectorAll('.card:not([data-animated])');
    newCards.forEach(function (card) {
      card.setAttribute('data-animated', '1');
      gsap.from(card, {
        opacity: 0,
        y: 8,
        duration: 0.3,
        ease: 'power2.out'
      });
    });
  });

  // ── Update sync timestamp ──
  document.addEventListener('htmx:afterSwap', function () {
    var el = document.getElementById('sync-status');
    if (el) {
      el.textContent = 'Synced ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
  });

  // ── Error handling ──
  document.addEventListener('htmx:responseError', function (e) {
    console.warn('HTMX poll error:', e.detail.xhr.status);
    if (window.showToast) {
      window.showToast('Connection issue — retrying...', 'error');
    }
  });

  // ── HTMX config ──
  document.addEventListener('DOMContentLoaded', function () {
    if (typeof htmx !== 'undefined') {
      htmx.config.defaultSwapStyle = 'innerHTML';
      htmx.config.defaultSettleDelay = 100;
    }
  });
})();
