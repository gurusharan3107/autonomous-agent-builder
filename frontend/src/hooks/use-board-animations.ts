import { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

/**
 * Board page — orchestrated section entrance with staggered card reveals.
 * Sections slide up with opacity, then cards within each section cascade.
 */
export function useBoardAnimations() {
  const containerRef = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const root = containerRef.current;
      if (!root) return;

      // Phase 1: Pipeline sections slide in
      const sections = Array.from(
        root.querySelectorAll<HTMLElement>("[data-board-section]"),
      );
      if (sections.length) {
        gsap.from(sections, {
          opacity: 0,
          y: 24,
          duration: 0.45,
          stagger: 0.1,
          ease: "power3.out",
          clearProps: "all",
        });
      }

      // Phase 2: Cards within sections stagger in (slightly delayed)
      const cards = Array.from(root.querySelectorAll<HTMLElement>("[data-slot='card']"));
      if (cards.length) {
        gsap.from(cards, {
          opacity: 0,
          y: 12,
          scale: 0.97,
          duration: 0.35,
          stagger: 0.04,
          delay: 0.3,
          ease: "power2.out",
          clearProps: "all",
        });
      }
    },
    { scope: containerRef },
  );

  return containerRef;
}
