import { useEffect, useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

interface AgentStatus {
  running: boolean;
  current_turn: number;
  max_turns: number;
  tokens_used: number;
  cost_usd: number;
}

export default function AgentPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Load chat history on mount
  useEffect(() => {
    const loadHistory = async () => {
      // Get session ID from localStorage
      const storedSessionId = localStorage.getItem("chat_session_id");
      if (!storedSessionId) {
        setHistoryLoaded(true);
        return;
      }

      try {
        const response = await fetch(`/api/agent/chat/history?session_id=${storedSessionId}`);
        if (!response.ok) {
          throw new Error("Failed to load history");
        }

        const data = await response.json();
        if (data.session_id && data.messages.length > 0) {
          // Restore session and messages
          setSessionId(data.session_id);
          const restoredMessages = data.messages.map((msg: any) => ({
            id: msg.id,
            role: msg.role,
            content: msg.content,
            timestamp: new Date(msg.timestamp),
          }));
          setMessages(restoredMessages);
        }
      } catch (error) {
        console.error("Failed to load chat history:", error);
      } finally {
        setHistoryLoaded(true);
      }
    };

    loadHistory();
  }, []);

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const response = await fetch("/api/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          message: input.trim(),
          session_id: sessionId,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to send message");
      }

      const data = await response.json();

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: data.response,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
      
      // Store session ID for conversation continuity
      if (data.session_id) {
        setSessionId(data.session_id);
        // Persist session ID to localStorage
        localStorage.setItem("chat_session_id", data.session_id);
      }
      
      if (data.status) {
        setStatus(data.status);
      }
    } catch (error: any) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: `Error: ${error.message}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex h-[calc(100vh-12rem)] flex-col space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Agent Chat</h1>
          <p className="text-xs text-muted-foreground mt-1">
            Interact with the Claude SDK agent
          </p>
        </div>
        {status && (
          <div className="flex items-center gap-2">
            <Badge variant={status.running ? "default" : "secondary"} className="text-[10px]">
              {status.running ? "Running" : "Idle"}
            </Badge>
            <span className="text-xs text-muted-foreground font-mono">
              Turn {status.current_turn}/{status.max_turns}
            </span>
            <span className="text-xs text-muted-foreground font-mono">
              ${status.cost_usd.toFixed(4)}
            </span>
          </div>
        )}
      </div>

      <Separator />

      <div className="flex-1 overflow-y-auto rounded-xl border bg-card shadow-sm">
        <div className="p-5 space-y-4">
          {!historyLoaded ? (
            <div className="flex h-full items-center justify-center py-20">
              <div className="text-center space-y-2">
                <div className="h-12 w-12 rounded-full bg-primary/10 mx-auto flex items-center justify-center">
                  <div className="h-6 w-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                </div>
                <p className="text-sm text-muted-foreground">Loading chat history...</p>
              </div>
            </div>
          ) : messages.length === 0 ? (
            <div className="flex h-full items-center justify-center py-20">
              <div className="text-center space-y-2">
                <div className="h-12 w-12 rounded-full bg-primary/10 mx-auto flex items-center justify-center">
                  <svg
                    className="h-6 w-6 text-primary"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
                    />
                  </svg>
                </div>
                <p className="text-sm text-muted-foreground">
                  Start a conversation with the agent
                </p>
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-3 ${
                  msg.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[80%] rounded-lg px-4 py-3 ${
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted"
                  }`}
                >
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                  <p className="text-[10px] mt-1 opacity-70">
                    {msg.timestamp.toLocaleTimeString()}
                  </p>
                </div>
              </div>
            ))
          )}
          {loading && (
            <div className="flex gap-3 justify-start">
              <div className="max-w-[80%] rounded-lg px-4 py-3 bg-muted">
                <div className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <div
                      key={i}
                      className="h-2 w-2 rounded-full bg-muted-foreground/30 animate-pulse"
                      style={{ animationDelay: `${i * 150}ms` }}
                    />
                  ))}
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      <div className="flex gap-2">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your message... (Shift+Enter for new line)"
          className="min-h-[80px] resize-none"
          disabled={loading}
        />
        <Button
          onClick={sendMessage}
          disabled={!input.trim() || loading}
          className="px-6"
        >
          Send
        </Button>
      </div>
    </div>
  );
}
