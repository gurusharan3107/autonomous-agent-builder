import { useState } from "react";

import { useRealtimeVoice } from "@/hooks/use-realtime-voice";

function SamanthaVoiceIcon() {
  return (
    <svg
      width="29"
      height="29"
      viewBox="0 0 64 64"
      fill="none"
      stroke="currentColor"
      strokeWidth="4"
      strokeLinecap="round"
      aria-hidden="true"
      data-samantha-voice-icon
    >
      <circle cx="32" cy="32" r="4.4" fill="currentColor" stroke="none" />
      <path d="M43 23a13 13 0 0 1 0 18" />
      <path d="M21 23a13 13 0 0 0 0 18" />
      <path d="M50.5 16a23.5 23.5 0 0 1 0 32" />
      <path d="M13.5 16a23.5 23.5 0 0 0 0 32" />
    </svg>
  );
}

export function SamanthaVoiceOrb() {
  const { voiceStatus, voiceError, startVoiceSession, stopVoiceSession, remoteAudioLevel } = useRealtimeVoice();
  const [hovered, setHovered] = useState(false);

  const hasError = voiceStatus === "error";
  const active = voiceStatus === "connected" || voiceStatus === "connecting";
  const scale = active ? 1 + remoteAudioLevel * 0.18 : 1;
  const ringOpacity = active ? 0.25 + remoteAudioLevel * 0.45 : 0;
  const glowOpacity = 0.015 + remoteAudioLevel * 0.085;
  const glowSize = 38 + remoteAudioLevel * 28;
  const visibleGlow = active;

  return (
    <div
      className="pointer-events-none fixed bottom-0 right-0 z-50 h-[min(34rem,72vh)] w-[min(34rem,72vw)]"
      data-samantha-voice-orb
    >
      {visibleGlow ? (
        <div
          className="absolute bottom-0 right-0"
          aria-hidden="true"
          style={{
            width: `${glowSize}vw`,
            height: `${glowSize * 1.1}vh`,
            background: `radial-gradient(ellipse at 100% 100%, rgb(192 68 10 / ${glowOpacity.toFixed(3)}) 0%, rgb(172 52 8 / ${(glowOpacity * 0.35).toFixed(3)}) 45%, transparent 75%)`,
          }}
        />
      ) : null}
      <button
        type="button"
        className="pointer-events-auto absolute bottom-5 right-5 flex flex-col items-center gap-2"
        style={{ background: "none", border: "none", padding: 0, cursor: "pointer", width: 32 }}
        onClick={() => {
          if (active) {
            stopVoiceSession();
          } else {
            void startVoiceSession();
          }
        }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        aria-label={active ? "End Samantha" : hasError ? "Retry Samantha" : "Activate Samantha"}
        title={active ? "End Samantha" : hasError ? (voiceError ?? "Voice error — click to retry") : undefined}
      >
        <span
          className="absolute rounded-full transition-opacity duration-150"
          aria-hidden="true"
          style={{
            width: 56,
            height: 56,
            top: "50%",
            left: "50%",
            transform: `translate(-50%, -50%) scale(${1 + remoteAudioLevel * 0.35})`,
            background: "radial-gradient(circle, rgb(0 0 0 / 0.18) 0%, transparent 70%)",
            opacity: ringOpacity,
            pointerEvents: "none",
          }}
        />
        <span
          className="relative inline-flex items-center justify-center rounded-full border transition-all duration-200"
          aria-hidden="true"
          style={{
            width: 44,
            height: 44,
            background: hasError
              ? "rgb(255 245 242 / 0.98)"
              : active
                ? "rgb(255 255 255 / 0.98)"
                : "rgb(255 255 255 / 0.94)",
            borderColor: hasError
              ? "rgb(200 60 40 / 0.42)"
              : active
                ? "rgb(0 0 0 / 0.22)"
                : "rgb(0 0 0 / 0.14)",
            color: hasError ? "rgb(170 42 32)" : "rgb(16 16 14)",
            boxShadow: hasError
              ? "0 0 10px 2px rgb(200 60 40 / 0.40)"
              : active
                ? `0 8px 22px rgb(0 0 0 / 0.20), 0 0 16px rgb(210 90 20 / 0.24), inset 0 1px 2px rgb(255 255 255 / 0.85)`
                : `0 6px 16px rgb(0 0 0 / 0.14), inset 0 1px 2px rgb(255 255 255 / 0.80)`,
            transform: `scale(${hovered ? 1.08 : scale})`,
          }}
        >
          <SamanthaVoiceIcon />
        </span>
        <span
          className="font-sans text-[9px] font-light uppercase tracking-[0.20em] transition-all duration-300"
          style={{
            color: hasError ? "rgb(180 50 30)" : "rgb(140 70 20)",
            opacity: hovered || hasError ? 1 : 0,
            marginTop: -2,
          }}
        >
          {hasError ? "error" : active ? "end" : "samantha"}
        </span>
      </button>
    </div>
  );
}
