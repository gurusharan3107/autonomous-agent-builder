/**
 * UI interactions — modals, collapse, toasts, relative time.
 */
(function () {
  // ── Pipeline section collapse/expand ──
  document.addEventListener('click', function (e) {
    var heading = e.target.closest('.pipeline-heading');
    if (!heading) return;
    var section = heading.closest('.pipeline-section');
    if (section) {
      section.classList.toggle('collapsed');
    }
  });

  // ── Modal open/close ──
  window.openModal = function (el) {
    el.style.display = 'flex';
    if (typeof gsap !== 'undefined') {
      var content = el.querySelector('.modal-content');
      gsap.fromTo(content,
        { opacity: 0, scale: 0.95, y: 10 },
        { opacity: 1, scale: 1, y: 0, duration: 0.25, ease: 'power2.out' }
      );
    }
  };

  window.closeModal = function (el) {
    if (typeof gsap !== 'undefined') {
      var content = el.querySelector('.modal-content');
      gsap.to(content, {
        opacity: 0,
        scale: 0.95,
        y: 10,
        duration: 0.2,
        ease: 'power2.in',
        onComplete: function () { el.style.display = 'none'; }
      });
    } else {
      el.style.display = 'none';
    }
  };

  // Close modal on backdrop click
  document.addEventListener('click', function (e) {
    if (e.target.classList.contains('modal')) {
      closeModal(e.target);
    }
  });

  // Close modal on Escape
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      var modal = document.querySelector('.modal[style*="flex"]');
      if (modal) closeModal(modal);
    }
  });

  // ── Toast notifications ──
  window.showToast = function (message, type) {
    type = type || 'info';
    var toast = document.createElement('div');
    toast.className = 'toast toast-' + type + ' slide-up';
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(function () {
      if (typeof gsap !== 'undefined') {
        gsap.to(toast, {
          opacity: 0, y: 10, duration: 0.3,
          onComplete: function () { toast.remove(); }
        });
      } else {
        toast.remove();
      }
    }, 4000);
  };

  // ── Relative time formatting ──
  function relativeTime(dateStr) {
    if (!dateStr) return '';
    var now = Date.now();
    var then = new Date(dateStr).getTime();
    var diff = Math.floor((now - then) / 1000);
    if (diff < 60) return diff + 's ago';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    return Math.floor(diff / 86400) + 'd ago';
  }

  // Convert timestamps on load
  document.querySelectorAll('[data-time]').forEach(function (el) {
    el.textContent = relativeTime(el.getAttribute('data-time'));
  });
})();
