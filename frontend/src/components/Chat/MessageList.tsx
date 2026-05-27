import { Copy, Check, ChevronDown, ChevronUp, Wrench, Terminal } from "lucide-react";
import { useState, useCallback, useMemo } from "react";
import type { ChatMessage } from "../../stores/chatStore";
import { MarkdownText } from "./MarkdownText";

const COLLAPSE_THRESHOLD = 500;
const PREVIEW_LENGTH = 300;

/** Split assistant message text into segments: regular text and tool-result blocks. */
function parseMessageSegments(text: string): MessageSegment[] {
  const segments: MessageSegment[] = [];

  // Match <tool_result name="...">...</tool_result> blocks
  const toolResultRe = /<tool_result\s+name=["']([^"']+)["']>\s*([\s\S]*?)<\/tool_result>/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = toolResultRe.exec(text)) !== null) {
    // Text before this tool result
    if (match.index > lastIndex) {
      const before = text.slice(lastIndex, match.index).trim();
      if (before) {
        segments.push({ type: "text", content: before });
      }
    }
    segments.push({
      type: "tool_result",
      name: match[1],
      content: match[2].trim(),
    });
    lastIndex = match.index + match[0].length;
  }

  // Remaining text after last tool result
  if (lastIndex < text.length) {
    const remaining = text.slice(lastIndex).trim();
    if (remaining) {
      segments.push({ type: "text", content: remaining });
    }
  }

  // If no tool results found, return the whole text as one segment
  if (segments.length === 0) {
    segments.push({ type: "text", content: text });
  }

  return segments;
}

type MessageSegment =
  | { type: "text"; content: string }
  | { type: "tool_result"; name: string; content: string };

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <>
      {messages.length === 0 && (
        <div className="chat-empty">
          <strong>等待你的第一条任务指令</strong>
          <p>可以直接说"检查冷小北现在能做什么""定位并修复最近一次失败，完成后运行验证""找一个最小改进点并自己验证"。</p>
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

  // For assistant messages, parse into segments (text + tool results)
  const segments = useMemo(() => {
    if (message.role !== "assistant") return null;
    return parseMessageSegments(message.text);
  }, [message.text, message.role]);

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
      {message.role === "assistant" && segments ? (
        <div className="message-segments">
          {segments.map((seg, i) =>
            seg.type === "tool_result" ? (
              <ToolResultBlock key={i} name={seg.name} content={seg.content} />
            ) : (
              <CollapsibleText key={i} text={seg.content} />
            )
          )}
        </div>
      ) : (
        <CollapsibleText text={message.text} />
      )}
    </article>
  );
}

/** Collapsible text block — auto-collapses if longer than threshold. */
function CollapsibleText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = text.length > COLLAPSE_THRESHOLD;

  const previewText = useMemo(() => {
    if (!isLong || expanded) return null;
    const slice = text.slice(0, PREVIEW_LENGTH);
    const lastBreak = Math.max(slice.lastIndexOf("\n"), slice.lastIndexOf("。"), slice.lastIndexOf(". "));
    return lastBreak > PREVIEW_LENGTH * 0.6 ? slice.slice(0, lastBreak + 1) : slice;
  }, [text, isLong, expanded]);

  const displayText = expanded || !isLong ? text : (previewText ?? text);

  return (
    <>
      <MarkdownText text={displayText} />
      {isLong && (
        <button
          className="collapse-toggle"
          onClick={() => setExpanded((v) => !v)}
          aria-label={expanded ? "收起" : "展开"}
        >
          {expanded ? (
            <><ChevronUp size={14} /> 收起</>
          ) : (
            <><ChevronDown size={14} /> 展开全部 ({Math.round(text.length / 1024)}KB)</>
          )}
        </button>
      )}
    </>
  );
}

/** Collapsible tool result block with icon and summary. */
function ToolResultBlock({ name, content }: { name: string; content: string }) {
  const [expanded, setExpanded] = useState(false);

  // Try to extract a short summary from the content
  const summary = useMemo(() => {
    try {
      const parsed = JSON.parse(content);
      if (parsed.error) return `❌ ${parsed.error}`;
      if (parsed.ok === false) return `❌ ${parsed.error || "执行失败"}`;
      if (Array.isArray(parsed.entries)) return `${parsed.entries.length} 个条目`;
      if (Array.isArray(parsed.results)) return `${parsed.results.length} 条结果`;
      if (Array.isArray(parsed.matches)) return `${parsed.matches.length} 个匹配`;
      if (parsed.path && parsed.bytes) return `${parsed.path} (${parsed.bytes}B)`;
      if (parsed.path && parsed.deleted) return `${parsed.path} 已删除`;
      if (parsed.path && parsed.replaced) return `${parsed.path} 已替换`;
      if (typeof parsed.ok === "boolean" && parsed.ok) return "✓ 成功";
      if (parsed.returncode === 0) return "exit 0";
      if (typeof parsed.returncode === "number") return `exit ${parsed.returncode}`;
      // Fallback: first 80 chars
      const str = JSON.stringify(parsed, null, 0);
      return str.length > 80 ? str.slice(0, 80) + "…" : str;
    } catch {
      return content.length > 80 ? content.slice(0, 80) + "…" : content;
    }
  }, [content]);

  const isShell = name === "shell_exec" || name === "shell_readonly";
  const Icon = isShell ? Terminal : Wrench;

  return (
    <div className={`tool-result-block ${expanded ? "expanded" : ""}`}>
      <button
        className="tool-result-header"
        onClick={() => setExpanded((v) => !v)}
        aria-label={expanded ? "收起工具结果" : "展开工具结果"}
      >
        <Icon size={13} className="tool-result-icon" />
        <span className="tool-result-name">{name}</span>
        <span className="tool-result-summary">{summary}</span>
        {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>
      {expanded && (
        <div className="tool-result-content">
          <pre>{content}</pre>
        </div>
      )}
    </div>
  );
}
