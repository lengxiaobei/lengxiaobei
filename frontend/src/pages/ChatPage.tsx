import { Send } from "lucide-react";
import { FormEvent, useState } from "react";
import { useChatStore } from "../stores/chatStore";

export function ChatPage() {
  const [text, setText] = useState("");
  const { messages, sending, send } = useChatStore();

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    await send(text);
    setText("");
  }

  return (
    <section className="page">
      <header>
        <h1>任务会话</h1>
        <p>Commander 负责规划，Dispatcher 负责工具调度，结果写入记忆树。</p>
      </header>
      <div className="chat-log">
        {messages.length === 0 && <div className="empty">等待第一条任务</div>}
        {messages.map((message, index) => (
          <article key={`${message.role}-${index}`} className={`message ${message.role}`}>
            <span>{message.role === "user" ? "你" : "冷小北"}</span>
            <p>{message.text}</p>
          </article>
        ))}
      </div>
      <form className="composer" onSubmit={onSubmit}>
        <input value={text} onChange={(event) => setText(event.target.value)} placeholder="输入任务或问题" />
        <button disabled={sending} title="发送">
          <Send size={18} />
        </button>
      </form>
    </section>
  );
}
