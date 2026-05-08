/**
 * Dark mode toggle — persists to localStorage, respects system preference on first visit.
 */
(function () {
  var STORAGE_KEY = 'aab-theme';
  var body = document.body;
  var toggle = document.getElementById('theme-toggle');
  var icon = document.getElementById('theme-icon');

  function setTheme(dark) {
    if (dark) {
      body.classList.add('dark-mode');
      if (icon) icon.textContent = '\u2600'; // sun
    } else {
      body.classList.remove('dark-mode');
      if (icon) icon.textContent = '\u263D'; // moon
    }
  }

  function isDark() {
    return body.classList.contains('dark-mode');
  }

  // Initialize from storage or system preference
  var stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'dark') {
    setTheme(true);
  } else if (stored === 'light') {
    setTheme(false);
  } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    setTheme(true);
  }

  // Toggle handler
  if (toggle) {
    toggle.addEventListener('click', function () {
      var nowDark = !isDark();
      setTheme(nowDark);
      localStorage.setItem(STORAGE_KEY, nowDark ? 'dark' : 'light');
    });
  }

  // Listen for system preference changes
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
      if (!localStorage.getItem(STORAGE_KEY)) {
        setTheme(e.matches);
      }
    });
  }
})();
