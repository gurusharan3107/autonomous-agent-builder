/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";

export type VoiceStatus = "idle" | "connecting" | "connected" | "error";
export type VoiceMode = "audio" | "text";
export type RealtimeVoiceMessageRole = "operator" | "assistant" | "system";

export interface RealtimeVoiceMessage {
  id: string;
  role: RealtimeVoiceMessageRole;
  content: string;
  timestamp: string;
  status: "streaming" | "complete";
}

interface RealtimeVoiceContextValue {
  voiceStatus: VoiceStatus;
  voiceError: string | null;
  voiceNotice: string | null;
  voiceMode: VoiceMode | null;
  voiceCallId: string | null;
  voiceEvents: string[];
  voiceMessages: RealtimeVoiceMessage[];
  remoteAudioLevel: number;
  sendRealtimeText: (text: string) => Promise<void>;
  startVoiceSession: (options?: { sessionId?: string | null }) => Promise<void>;
  stopVoiceSession: () => void;
  clearVoiceTranscript: () => void;
}

const RealtimeVoiceContext = createContext<RealtimeVoiceContextValue | null>(null);

async function getResponseError(response: Response): Promise<string> {
  const text = await response.text();
  if (text) {
    try {
      const payload = JSON.parse(text) as { detail?: unknown; error?: unknown };
      if (payload.detail) {
        return typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
      }
      if (payload.error) {
        return typeof payload.error === "string" ? payload.error : JSON.stringify(payload.error);
      }
    } catch {
      return text;
    }
    return text;
  }
  return response.statusText || `Request failed with status ${response.status}`;
}

function waitForVoiceIceGathering(peer: RTCPeerConnection) {
  if (peer.iceGatheringState === "complete") return Promise.resolve();
  return new Promise<void>((resolve) => {
    const timeout = window.setTimeout(resolve, 1200);
    peer.addEventListener(
      "icegatheringstatechange",
      () => {
        if (peer.iceGatheringState === "complete") {
          window.clearTimeout(timeout);
          resolve();
        }
      },
      { once: true },
    );
  });
}

function getMicrophoneStreamWithTimeout(timeoutMs = 1500): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) {
    return Promise.reject(
      new DOMException("Browser mediaDevices.getUserMedia is unavailable.", "NotFoundError"),
    );
  }

  return new Promise<MediaStream>((resolve, reject) => {
    let settled = false;
    const timeout = window.setTimeout(() => {
      settled = true;
      reject(new DOMException("Microphone did not respond before text-mode fallback.", "TimeoutError"));
    }, timeoutMs);

    navigator.mediaDevices.getUserMedia({ audio: true }).then(
      (stream) => {
        if (settled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        settled = true;
        window.clearTimeout(timeout);
        resolve(stream);
      },
      (error) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timeout);
        reject(error);
      },
    );
  });
}

function microphoneUnavailableMessage(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === "TimeoutError") {
      return "Microphone did not respond quickly. Realtime text mode is available in the Voice tab.";
    }
    if (error.name === "NotFoundError" || error.name === "DevicesNotFoundError") {
      return "This browser or macOS did not expose a microphone. If one is connected, check the input device and browser microphone permission. Realtime text mode is available in the Voice tab.";
    }
    if (error.name === "NotAllowedError" || error.name === "PermissionDeniedError") {
      return "Microphone permission is blocked. Realtime text mode is available in the Voice tab.";
    }
  }
  return "Microphone input is unavailable in this browser. Check the input device and browser microphone permission. Realtime text mode is available in the Voice tab.";
}

function nowIso() {
  return new Date().toISOString();
}

function createVoiceMessage(role: RealtimeVoiceMessageRole, content: string, status: "streaming" | "complete" = "complete") {
  const randomPart = Math.random().toString(36).slice(2, 8);
  return {
    id: `realtime-${Date.now()}-${randomPart}`,
    role,
    content,
    timestamp: nowIso(),
    status,
  };
}

function eventString(event: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = event[key];
    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }
  return "";
}

function nestedEventString(event: Record<string, unknown>, objectKey: string, keys: string[]) {
  const value = event[objectKey];
  if (!value || typeof value !== "object") return "";
  return eventString(value as Record<string, unknown>, keys);
}

export function RealtimeVoiceProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>("idle");
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [voiceNotice, setVoiceNotice] = useState<string | null>(null);
  const [voiceMode, setVoiceMode] = useState<VoiceMode | null>(null);
  const [voiceCallId, setVoiceCallId] = useState<string | null>(null);
  const [boundSessionId, setBoundSessionId] = useState<string | null>(null);
  const [voiceEvents, setVoiceEvents] = useState<string[]>([]);
  const [voiceMessages, setVoiceMessages] = useState<RealtimeVoiceMessage[]>([]);
  const voicePeerRef = useRef<RTCPeerConnection | null>(null);
  const voiceDataChannelRef = useRef<RTCDataChannel | null>(null);
  const voiceStreamRef = useRef<MediaStream | null>(null);
  const voiceAudioRef = useRef<HTMLAudioElement | null>(null);
  const voiceConnectTimeoutRef = useRef<number | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const analyserFrameRef = useRef<number | null>(null);
  const [remoteAudioLevel, setRemoteAudioLevel] = useState(0);

  const clearVoiceTranscript = useCallback(() => {
    setVoiceEvents([]);
    setVoiceMessages([]);
  }, []);

  const appendVoiceEvent = (label: string) => {
    setVoiceEvents((current) => [...current.slice(-5), label]);
  };

  const appendVoiceMessage = (role: RealtimeVoiceMessageRole, content: string) => {
    const trimmed = content.trim();
    if (!trimmed) return;
    setVoiceMessages((current) => [...current, createVoiceMessage(role, trimmed)]);
  };

  const appendAssistantDelta = (delta: string) => {
    if (!delta) return;
    setVoiceMessages((current) => {
      const last = current.at(-1);
      if (last?.role === "assistant" && last.status === "streaming") {
        return [
          ...current.slice(0, -1),
          {
            ...last,
            content: `${last.content}${delta}`,
            timestamp: nowIso(),
          },
        ];
      }
      return [...current, createVoiceMessage("assistant", delta, "streaming")];
    });
  };

  const completeAssistantMessage = (content?: string) => {
    setVoiceMessages((current) => {
      const last = current.at(-1);
      const completedText = content?.trim();
      if (last?.role === "assistant" && last.status === "streaming") {
        return [
          ...current.slice(0, -1),
          {
            ...last,
            content: completedText && completedText.length >= last.content.length ? completedText : last.content,
            timestamp: nowIso(),
            status: "complete",
          },
        ];
      }
      if (
        completedText &&
        last?.role === "assistant" &&
        last.status === "complete" &&
        last.content.trim() === completedText
      ) {
        return current;
      }
      if (completedText) {
        return [...current, createVoiceMessage("assistant", completedText)];
      }
      return current;
    });
  };

  const handleRealtimeEvent = (event: Record<string, unknown>) => {
    const eventType = String(event.type ?? "realtime event");
    appendVoiceEvent(eventType);

    if (eventType === "conversation.item.input_audio_transcription.completed") {
      const transcript = eventString(event, ["transcript", "text"]).trim();
      if (!transcript) return;
      appendVoiceMessage("operator", transcript);
      return;
    }

    if (
      eventType === "response.output_audio_transcript.delta" ||
      eventType === "response.output_text.delta"
    ) {
      appendAssistantDelta(eventString(event, ["delta", "transcript", "text"]));
      return;
    }

    if (
      eventType === "response.output_audio_transcript.done" ||
      eventType === "response.output_text.done" ||
      eventType === "response.content_part.done"
    ) {
      completeAssistantMessage(
        eventString(event, ["transcript", "text"]) ||
          nestedEventString(event, "part", ["transcript", "text"]) ||
          nestedEventString(event, "content", ["transcript", "text"]),
      );
      return;
    }

    if (eventType === "response.done") {
      completeAssistantMessage();
    }
  };

  const stopAudioAnalyser = useCallback(() => {
    if (analyserFrameRef.current !== null) {
      cancelAnimationFrame(analyserFrameRef.current);
      analyserFrameRef.current = null;
    }
    analyserRef.current?.disconnect();
    analyserRef.current = null;
    audioCtxRef.current?.close().catch(() => undefined);
    audioCtxRef.current = null;
    setRemoteAudioLevel(0);
  }, []);

  const startAudioAnalyser = useCallback((stream: MediaStream) => {
    stopAudioAnalyser();
    try {
      const ctx = new AudioContext();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 64;
      analyser.smoothingTimeConstant = 0.75;
      ctx.createMediaStreamSource(stream).connect(analyser);
      audioCtxRef.current = ctx;
      analyserRef.current = analyser;
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((a, b) => a + b, 0) / data.length;
        setRemoteAudioLevel(avg / 255);
        analyserFrameRef.current = requestAnimationFrame(tick);
      };
      analyserFrameRef.current = requestAnimationFrame(tick);
    } catch {
      // Web Audio unavailable — level stays 0
    }
  }, [stopAudioAnalyser]);

  const stopVoiceSession = useCallback(() => {
    if (voiceConnectTimeoutRef.current !== null) {
      window.clearTimeout(voiceConnectTimeoutRef.current);
      voiceConnectTimeoutRef.current = null;
    }
    stopAudioAnalyser();
    voiceDataChannelRef.current?.close();
    voicePeerRef.current?.close();
    voiceStreamRef.current?.getTracks().forEach((track) => track.stop());
    voiceAudioRef.current?.remove();
    voiceDataChannelRef.current = null;
    voicePeerRef.current = null;
    voiceStreamRef.current = null;
    voiceAudioRef.current = null;
    setVoiceCallId(null);
    setBoundSessionId(null);
    setVoiceMode(null);
    setVoiceNotice(null);
    setVoiceError(null);
    setVoiceStatus("idle");
  }, [stopAudioAnalyser]);

  const sendRealtimeText = async (text: string) => {
    const message = text.trim();
    const dataChannel = voiceDataChannelRef.current;
    if (!message) return;
    const canUseRealtimeChannel =
      voiceMode !== "text" &&
      voiceStatus === "connected" &&
      dataChannel &&
      dataChannel.readyState === "open";
    const controlResponse = await fetch("/api/realtime/text-control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        call_id: voiceCallId,
        session_id: boundSessionId,
        fallback_to_agent: !canUseRealtimeChannel,
      }),
    });
    if (!controlResponse.ok) {
      throw new Error(await getResponseError(controlResponse));
    }
    const control = (await controlResponse.json()) as {
      handled?: boolean;
      assistant_message?: string;
      tool_name?: string;
      route?: string;
    };
    if (control.handled) {
      appendVoiceMessage("operator", message);
      appendVoiceMessage("assistant", control.assistant_message || "Builder status is unavailable right now.");
      appendVoiceEvent(control.tool_name ? `text control ${control.tool_name}` : "text control handled");
      if (typeof control.route === "string" && control.route.startsWith("/")) {
        const delegatedSessionId = new URL(control.route, window.location.origin).searchParams.get("session") || "";
        navigate(control.route);
        appendVoiceEvent(`dashboard navigation ${control.route}`);
        window.dispatchEvent(
          new CustomEvent("aab:voice-navigation-request", {
            detail: { route: control.route, session_id: delegatedSessionId },
          }),
        );
      }
      window.dispatchEvent(new CustomEvent("aab:voice-transcript-sync"));
      return;
    }
    if (!canUseRealtimeChannel || !dataChannel) {
      throw new Error("Realtime is not connected yet.");
    }
    dataChannel.send(
      JSON.stringify({
        type: "conversation.item.create",
        item: {
          type: "message",
          role: "user",
          content: [
            {
              type: "input_text",
              text: message,
            },
          ],
        },
      }),
    );
    dataChannel.send(JSON.stringify({ type: "response.create" }));
    appendVoiceMessage("operator", message);
    appendVoiceEvent("realtime text sent");
    window.dispatchEvent(new CustomEvent("aab:voice-transcript-sync"));
  };

  const startVoiceSession = async (options?: { sessionId?: string | null }) => {
    if (voiceStatus === "connecting" || voiceStatus === "connected") return;
    setVoiceStatus("connecting");
    setVoiceError(null);
    setVoiceNotice(null);
    setVoiceEvents([]);
    setVoiceMessages([]);
    setVoiceCallId(null);
    setVoiceMode(null);
    const requestedSessionId = options?.sessionId ?? null;
    const voiceSessionHeaders: Record<string, string> = {
      "Content-Type": "application/sdp",
      "X-Agent-Session-Mode": requestedSessionId ? "current" : "fresh",
    };
    if (requestedSessionId) {
      voiceSessionHeaders["X-Agent-Session-Id"] = requestedSessionId;
    }

    try {
      const peer = new RTCPeerConnection();
      voicePeerRef.current = peer;

      const audio = document.createElement("audio");
      audio.autoplay = true;
      voiceAudioRef.current = audio;
      peer.ontrack = (event) => {
        audio.srcObject = event.streams[0];
        startAudioAnalyser(event.streams[0]);
      };

      let stream: MediaStream | null = null;
      let microphoneNotice: string | null = null;
      try {
        const audioStream = await getMicrophoneStreamWithTimeout();
        stream = audioStream;
        voiceStreamRef.current = audioStream;
        audioStream.getTracks().forEach((track) => peer.addTrack(track, audioStream));
      } catch (error) {
        microphoneNotice = microphoneUnavailableMessage(error);
        peer.addTransceiver("audio", { direction: "recvonly" });
      }

      const dataChannel = peer.createDataChannel("oai-events");
      voiceDataChannelRef.current = dataChannel;
      const markRealtimeConnected = () => {
        if (voiceConnectTimeoutRef.current !== null) {
          window.clearTimeout(voiceConnectTimeoutRef.current);
          voiceConnectTimeoutRef.current = null;
        }
        setVoiceStatus("connected");
        setVoiceMode(stream ? "audio" : "text");
        setVoiceNotice(microphoneNotice);
        appendVoiceEvent("oai-events connected");
        if (microphoneNotice) {
          appendVoiceEvent("realtime text mode");
        }
        window.dispatchEvent(new CustomEvent("aab:voice-transcript-sync"));
      };
      voiceConnectTimeoutRef.current = window.setTimeout(() => {
        if (voiceDataChannelRef.current?.readyState === "open") {
          markRealtimeConnected();
          return;
        }
        stopVoiceSession();
        setVoiceStatus("error");
        setVoiceError(
          "Realtime did not finish connecting. Check network/API availability, then start voice again.",
        );
      }, 12000);
      dataChannel.addEventListener("open", () => {
        markRealtimeConnected();
        dataChannel.send(
          JSON.stringify({
            type: "response.create",
            response: {
              instructions: "Say only: Hi there!",
              metadata: { source: "builder_voice_activation_greeting" },
            },
          }),
        );
      });
      dataChannel.addEventListener("message", (message) => {
        try {
          const event = JSON.parse(message.data) as Record<string, unknown>;
          handleRealtimeEvent(event);
        } catch {
          appendVoiceEvent("unparsed realtime event");
        }
        window.dispatchEvent(new CustomEvent("aab:voice-transcript-sync"));
      });

      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      await waitForVoiceIceGathering(peer);
      const localSdp = peer.localDescription?.sdp ?? "";
      if (!localSdp.trim()) {
        throw new Error("Browser did not create a Realtime SDP offer.");
      }

      const response = await fetch("/api/realtime/session", {
        method: "POST",
        headers: voiceSessionHeaders,
        body: localSdp,
      });
      if (!response.ok) {
        throw new Error(await getResponseError(response));
      }

      setVoiceCallId(response.headers.get("X-Realtime-Call-Id"));
      const boundSessionId = response.headers.get("X-Agent-Session-Id");
      if (boundSessionId) {
        setBoundSessionId(boundSessionId);
        window.dispatchEvent(
          new CustomEvent("aab:voice-session-bound", { detail: { sessionId: boundSessionId } }),
        );
      }
      await peer.setRemoteDescription({ type: "answer", sdp: await response.text() });
      if (dataChannel.readyState === "open") {
        markRealtimeConnected();
      }
    } catch (error) {
      stopVoiceSession();
      setVoiceStatus("error");
      setVoiceError(error instanceof Error ? error.message : "Realtime voice session failed.");
    }
  };

  useEffect(() => () => stopVoiceSession(), [stopVoiceSession]);

  useEffect(() => {
    if (!boundSessionId) return undefined;
    const stream = new EventSource(
      `/api/agent/chat/stream?session_id=${encodeURIComponent(boundSessionId)}`,
    );
    const recordVoiceEvent = (label: string) => {
      setVoiceEvents((current) => [label.toLowerCase(), ...current].slice(0, 6));
    };
    const navigateFromPayload = (payload: Record<string, unknown>) => {
      const route = typeof payload.route === "string" ? payload.route : "";
      const nextSessionId = typeof payload.session_id === "string" ? payload.session_id : "";
      if (nextSessionId) {
        setBoundSessionId(nextSessionId);
        window.dispatchEvent(
          new CustomEvent("aab:voice-session-bound", { detail: { sessionId: nextSessionId } }),
        );
      }
      if (!route.startsWith("/")) return;
      navigate(route);
      recordVoiceEvent(`dashboard navigation ${route}`);
    };
    stream.addEventListener("event", (event) => {
      try {
        const message = event as MessageEvent<string>;
        const item = JSON.parse(message.data) as {
          type?: string;
          payload?: Record<string, unknown>;
        };
        const payload = item.payload ?? {};
        if (item.type === "voice_navigation_request") {
          navigateFromPayload(payload);
          window.dispatchEvent(new CustomEvent("aab:voice-navigation-request", { detail: payload }));
          return;
        }
        if (item.type === "voice_control_action") {
          navigateFromPayload(payload);
          window.dispatchEvent(new CustomEvent("aab:voice-control-action", { detail: payload }));
          return;
        }
        if (item.type === "runtime_settings_updated") {
          window.dispatchEvent(
            new CustomEvent("aab:runtime-settings-updated", { detail: payload }),
          );
        }
      } catch {
        recordVoiceEvent("unparsed voice control event");
      }
    });
    stream.onerror = () => {
      stream.close();
    };
    return () => {
      stream.close();
    };
  }, [boundSessionId, navigate]);

  return (
    <RealtimeVoiceContext.Provider
      value={{
        voiceStatus,
        voiceError,
        voiceNotice,
        voiceMode,
        voiceCallId,
        voiceEvents,
        voiceMessages,
        remoteAudioLevel,
        sendRealtimeText,
        startVoiceSession,
        stopVoiceSession,
        clearVoiceTranscript,
      }}
    >
      {children}
    </RealtimeVoiceContext.Provider>
  );
}

export function useRealtimeVoice() {
  const context = useContext(RealtimeVoiceContext);
  if (!context) {
    throw new Error("useRealtimeVoice must be used inside RealtimeVoiceProvider");
  }
  return context;
}
