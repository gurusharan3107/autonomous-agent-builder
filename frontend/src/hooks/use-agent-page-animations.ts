import { useRef } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

export function useAgentPageAnimations(activeInspector: "sessions" | "evidence" | null) {
  const containerRef = useRef<HTMLDivElement>(null);

  useGSAP(
    () => {
      const root = containerRef.current;
      if (!root) return;

      const sections = Array.from(
        root.querySelectorAll<HTMLElement>("[data-agent-stage='section']"),
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

      const cards = Array.from(
        root.querySelectorAll<HTMLElement>("[data-agent-stage='card']"),
      );
      if (cards.length) {
        gsap.from(cards, {
          opacity: 0,
          y: 16,
          duration: 0.35,
          stagger: 0.04,
          delay: 0.18,
          ease: "power2.out",
          clearProps: "all",
        });
      }
    },
    { scope: containerRef },
  );

  useGSAP(
    () => {
      const root = containerRef.current;
      if (!root || !activeInspector) return;

      const inspector = root.querySelector<HTMLElement>("[data-agent-inspector='true']");
      if (!inspector) return;

      gsap.fromTo(
        inspector,
        { opacity: 0, x: 8, y: 16 },
        {
          opacity: 1,
          x: 0,
          y: 0,
          duration: 0.3,
          ease: "power2.out",
          clearProps: "all",
        },
      );
    },
    { scope: containerRef, dependencies: [activeInspector] },
  );

  return containerRef;
}
