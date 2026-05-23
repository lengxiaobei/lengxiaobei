import type { ChatMessage } from "../../stores/chatStore";

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  return <div className="chat-log">{messages.length === 0 && <div className="empty">等待第一条任务</div>}{messages.map((message, index) => <article key={`${message.role}-${index}`} className={`message ${message.role}`}><span>{message.role === "user" ? "你" : "冷小北"}</span><p>{message.text}</p></article>)}</div>;
}
