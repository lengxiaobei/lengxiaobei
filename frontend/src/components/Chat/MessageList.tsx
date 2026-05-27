import { Copy, Check } from "lucide-react";
import { useState, useCallback } from "react";
import type { ChatMessage } from "../../stores/chatStore";
import { MarkdownText } from "./MarkdownText";

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <>
      {messages.length === 0 && (
        <div className="chat-empty">
          <strong>等待你的第一条任务指令</strong>
          <p>可以直接说"检查冷小北现在能做什么""复盘最近一次失败并给出修复动作""找一个最小改进点并自己验证"。</p>
        </div>
      )}
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}
    </>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const [copied, setCopied] = useState(false);

  const copyText = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(message.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  }, [message.text]);

  return (
    <article className={`message ${message.role}`}>
      <div className="message-meta">
        <span>{message.role === "user" ? "你" : "冷小北"}</span>
        <time>{new Date(message.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
        {message.role === "assistant" && (
          <button className="copy-btn" onClick={copyText} title="复制" aria-label="复制消息">
            {copied ? <Check size={13} /> : <Copy size={13} />}
          </button>
        )}
      </div>
      {message.role === "assistant" ? (
        <MarkdownText text={message.text} />
      ) : (
        <p>{message.text}</p>
      )}
    </article>
  );
}
