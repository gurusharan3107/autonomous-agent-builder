/**
 * GSAP animations — progressive enhancement (graceful if GSAP not loaded).
 */
(function () {
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  ready(function () {
    if (typeof gsap === 'undefined') return;

    // Register ScrollTrigger if available
    if (typeof ScrollTrigger !== 'undefined') {
      gsap.registerPlugin(ScrollTrigger);
    }

    // ── Card entrance animations (staggered) ──
    var cards = document.querySelectorAll('.card, .kpi-card, .pipeline-section');
    if (cards.length) {
      gsap.from(cards, {
        opacity: 0,
        y: 16,
        duration: 0.4,
        stagger: 0.06,
        ease: 'power2.out',
        clearProps: 'all'
      });
    }

    // ── KPI cards — scroll-triggered entrance on metrics page ──
    var kpiCards = document.querySelectorAll('.kpi-card');
    if (kpiCards.length && typeof ScrollTrigger !== 'undefined') {
      kpiCards.forEach(function (card, i) {
        gsap.from(card, {
          scrollTrigger: {
            trigger: card,
            start: 'top 90%',
            once: true
          },
          opacity: 0,
          y: 20,
          duration: 0.5,
          delay: i * 0.1,
          ease: 'power2.out',
          clearProps: 'all'
        });
      });
    }

    // ── Cost bar chart animation ──
    var bars = document.querySelectorAll('.cost-bar');
    if (bars.length) {
      bars.forEach(function (bar) {
        var h = bar.style.height;
        bar.style.height = '0%';
        gsap.to(bar, {
          height: h,
          duration: 0.6,
          delay: 0.3,
          ease: 'power2.out'
        });
      });
    }

    // ── Pipeline stepper active glow ──
    var activeStep = document.querySelector('.stepper-step.active');
    if (activeStep) {
      gsap.to(activeStep, {
        boxShadow: '0 0 12px rgba(0, 113, 227, 0.3)',
        repeat: -1,
        yoyo: true,
        duration: 1.5,
        ease: 'sine.inOut'
      });
    }
  });

  // ── Highlight new/changed elements after HTMX swap ──
  window.highlightOnUpdate = function (el) {
    if (typeof gsap === 'undefined') return;
    gsap.fromTo(el,
      { borderColor: 'rgba(0, 113, 227, 0.6)' },
      { borderColor: 'transparent', duration: 1.5, ease: 'power2.out' }
    );
  };

  // ── Animate new cards inserted by HTMX ──
  window.animateCardsEntrance = true;
})();
