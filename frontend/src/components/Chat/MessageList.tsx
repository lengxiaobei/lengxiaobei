import { Copy, Check, ChevronDown, ChevronUp, Brain, Zap, RefreshCw, Route } from "lucide-react";
import { useState, useCallback, useMemo } from "react";
import type { ChatMessage } from "../../stores/chatStore";
import { MarkdownText } from "./MarkdownText";
import { ToolCallCard } from "./ToolCallCard";

const COLLAPSE_THRESHOLD = 500;
const PREVIEW_LENGTH = 300;

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <>
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}
    </>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const isLong = message.text.length > COLLAPSE_THRESHOLD;
  const hasToolCalls = (message.toolCalls?.length ?? 0) > 0;
  const hasPlan = !!message.plan && message.plan.intent !== "chat";

  const previewText = useMemo(() => {
    if (!isLong || expanded) return null;
    const slice = message.text.slice(0, PREVIEW_LENGTH);
    const lastBreak = Math.max(slice.lastIndexOf("\n"), slice.lastIndexOf("。"), slice.lastIndexOf(". "));
    return lastBreak > PREVIEW_LENGTH * 0.6 ? slice.slice(0, lastBreak + 1) : slice;
  }, [message.text, isLong, expanded]);

  const copyText = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(message.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  }, [message.text]);

  const displayText = expanded || !isLong ? message.text : (previewText ?? message.text);

  return (
    <article className={`message ${message.role}`}>
      {/* Meta row */}
      <div className="message-meta">
        <span>{message.role === "user" ? "你" : "冷小北"}</span>
        <time>{new Date(message.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
        {message.role === "assistant" && (
          <>
            {hasPlan && <PlanBadge plan={message.plan!} />}
            {hasToolCalls && (
              <span className="msg-stat">
                <Zap size={11} />
                {message.toolCalls!.length} 工具
              </span>
            )}
            {message.iterations != null && message.iterations > 0 && (
              <span className="msg-stat">
                <RefreshCw size={11} />
                {message.iterations} 轮
              </span>
            )}
            {message.elapsedMs != null && (
              <span className="msg-stat">
                <ClockMini />
                {message.elapsedMs < 1000
                  ? `${message.elapsedMs}ms`
                  : `${(message.elapsedMs / 1000).toFixed(1)}s`}
              </span>
            )}
            <button className="copy-btn" onClick={copyText} title="复制" aria-label="复制消息">
              {copied ? <Check size={13} /> : <Copy size={13} />}
            </button>
          </>
        )}
      </div>

      {/* Tool calls — OpenClaw-style collapsible cards */}
      {hasToolCalls && (
        <div className="tool-calls-strip">
          {message.toolCalls!.map((tc, i) => (
            <ToolCallCard key={`${tc.name}-${i}`} call={tc} />
          ))}
        </div>
      )}

      {/* Text body */}
      <div className="message-body">
        {message.role === "assistant" ? (
          <MarkdownText text={displayText} />
        ) : (
          <p>{displayText}</p>
        )}
      </div>

      {/* Expand/collapse */}
      {isLong && (
        <button
          className="collapse-toggle"
          onClick={() => setExpanded((v) => !v)}
          aria-label={expanded ? "收起" : "展开"}
        >
          {expanded ? (
            <><ChevronUp size={14} /> 收起</>
          ) : (
            <><ChevronDown size={14} /> 展开全部 ({Math.round(message.text.length / 1024)}KB)</>
          )}
        </button>
      )}

      {/* Trace link */}
      {message.role === "assistant" && message.runId && (
        <button
          className="trace-link"
          onClick={() => {
            // Switch to trace tab and select this run
            const event = new CustomEvent("lengxiaobei:show-trace", { detail: { runId: message.runId } });
            window.dispatchEvent(event);
          }}
          style={{
            display: "inline-flex", alignItems: "center", gap: 4,
            background: "none", border: "1px solid var(--c-border)", borderRadius: 4,
            padding: "2px 8px", fontSize: 11, color: "var(--c-text-muted)",
            cursor: "pointer", marginTop: 4,
          }}
          title="查看完整执行轨迹"
        >
          <Route size={11} />
          查看轨迹
        </button>
      )}
    </article>
  );
}

function PlanBadge({ plan }: { plan: NonNullable<ChatMessage["plan"]> }) {
  return (
    <span className="plan-badge" title={plan.reason}>
      <Brain size={11} />
      {plan.intent === "agent_loop" ? "自主执行" : plan.intent}
    </span>
  );
}

function ClockMini() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}
