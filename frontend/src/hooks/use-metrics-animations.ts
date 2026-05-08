import { useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP, ScrollTrigger);

/**
 * Metrics page — KPI cards cascade from ScrollTrigger,
 * cost bars animate height from zero with orchestrated timing.
 */
export function useMetricsAnimations() {
  const containerRef = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const root = containerRef.current;
      if (!root) return;

      // KPI cards — staggered entrance on scroll
      const kpiCards = Array.from(root.querySelectorAll<HTMLElement>("[data-kpi]"));
      if (kpiCards.length) {
        gsap.from(kpiCards, {
          scrollTrigger: {
            trigger: kpiCards[0],
            start: "top 90%",
            once: true,
          },
          opacity: 0,
          y: 20,
          scale: 0.97,
          duration: 0.45,
          stagger: 0.08,
          ease: "power3.out",
          clearProps: "all",
        });
      }

      // Cost bars — animate height from 0 with staggered delay
      const bars = Array.from(root.querySelectorAll<HTMLElement>("[data-cost-bar]"));
      bars.forEach((bar, i) => {
        const targetHeight = bar.style.height;
        gsap.fromTo(
          bar,
          { height: "0%" },
          {
            height: targetHeight,
            duration: 0.5,
            delay: 0.4 + i * 0.02,
            ease: "power2.out",
          },
        );
      });

      // Table rows — subtle fade
      const rows = Array.from(root.querySelectorAll<HTMLElement>("tbody tr"));
      if (rows.length) {
        gsap.from(rows, {
          opacity: 0,
          x: -8,
          duration: 0.3,
          stagger: 0.03,
          delay: 0.6,
          ease: "power2.out",
          clearProps: "all",
        });
      }
    },
    { scope: containerRef },
  );

  return containerRef;
}
