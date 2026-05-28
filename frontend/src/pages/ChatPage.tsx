import { Bot, BrainCircuit, PlugZap, RotateCcw } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useRef } from "react";
import { InputArea } from "../components/Chat/InputArea";
import { MessageList } from "../components/Chat/MessageList";
import { useChatStore } from "../stores/chatStore";
import { useSystemStore } from "../stores/systemStore";

export function ChatPage() {
  const { messages, sending, send, clear } = useChatStore();
  const { status, wsConnected } = useSystemStore();
  const logRef = useRef<HTMLDivElement>(null);
  const hasMessages = messages.length > 0;

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  return (
    <section className="page chat-page">
      {/* Compact toolbar — title + mini status + clear */}
      <header className="chat-toolbar">
        <div className="chat-toolbar-left">
          <span className="chat-toolbar-title">冷小北</span>
          <span className="chat-toolbar-sep">·</span>
          <StatusBadge icon={<PlugZap size={12} />} label={wsConnected ? "在线" : "离线"} ok={wsConnected} />
          <StatusBadge icon={<BrainCircuit size={12} />} label={status?.model?.model || "…"} ok={!!status?.model?.api_key_configured} />
        </div>
        <button className="ghost-button ghost-button-sm" onClick={clear} title="清空消息">
          <RotateCcw size={14} />
          <span>清屏</span>
        </button>
      </header>

      {/* Chat log — takes all remaining vertical space */}
      <div className="chat-log" ref={logRef}>
        {!hasMessages && !sending && (
          <div className="chat-empty">
            <strong>和冷小北开始对话</strong>
            <p>输入问题或任务，冷小北会用记忆、工具和技能链路来回答。</p>
          </div>
        )}
        <MessageList messages={messages} />
        {sending && (
          <article className="message assistant pending">
            <div className="message-meta">
              <span>冷小北</span>
              <time>执行中</time>
            </div>
            <p style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Bot size={16} />
              <span>
                正在处理
                <span style={{ opacity: 0.6 }}> · 可在「轨迹」页查看详细执行过程</span>
              </span>
            </p>
          </article>
        )}
      </div>

      <InputArea sending={sending} onSend={send} />
    </section>
  );
}

function StatusBadge({ icon, label, ok = true }: { icon: ReactNode; label: string; ok?: boolean }) {
  return (
    <span className={`status-badge ${ok ? "" : "status-badge-warn"}`}>
      {icon}
      <span>{label}</span>
    </span>
  );
}
