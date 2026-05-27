import { Bot, BrainCircuit, Database, PlugZap, RotateCcw, Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useRef } from "react";
import { InputArea } from "../components/Chat/InputArea";
import { MessageList } from "../components/Chat/MessageList";
import { useChatStore } from "../stores/chatStore";
import { useSystemStore } from "../stores/systemStore";

const suggestions = ["巡检通道运行时", "反思最近失败", "整理我的长期记忆", "总结冷小北能力状态"];

export function ChatPage() {
  const { messages, sending, send, clear } = useChatStore();
  const { status, wsConnected } = useSystemStore();
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  return (
    <section className="page chat-page">
      <header className="chat-header">
        <div>
          <span className="eyebrow">LENGXIAOBEI MISSION DECK</span>
          <h1>冷小北任务中枢</h1>
          <p>把意图交给冷小北，由它自己的通道、记忆、反思、技能和工具链路完成任务。</p>
        </div>
        <button className="ghost-button" onClick={clear} title="清空当前界面消息">
          <RotateCcw size={16} />
          <span>清屏</span>
        </button>
      </header>
      <div className="home-status">
        <StatusTile icon={<PlugZap size={18} />} label="连接" value={wsConnected ? "实时在线" : status?.status === "running" ? "HTTP 在线" : "连接中"} tone={wsConnected ? "ok" : "warn"} />
        <StatusTile icon={<BrainCircuit size={18} />} label="模型" value={status?.model?.model || "未配置"} detail={status?.model?.api_key_configured ? status.model.provider : "缺少 API Key"} tone={status?.model?.api_key_configured ? "ok" : "bad"} />
        <StatusTile icon={<Database size={18} />} label="自治" value={String(status?.autonomy?.last_goal || "待运行")} detail={status?.autonomy?.run_count ? `${status.autonomy.run_count} 轮` : "尚无记录"} tone="neutral" />
      </div>
      <div className="chat-log" ref={logRef}>
        <MessageList messages={messages} />
        {sending && (
          <article className="message assistant pending">
            <div className="message-meta">
              <span>冷小北</span>
              <time>思考中</time>
            </div>
            <p><Bot size={16} /> 正在组织回复...</p>
          </article>
        )}
      </div>
      <div className="prompt-strip">
        <Sparkles size={15} />
        {suggestions.map((item) => (
          <button key={item} type="button" onClick={() => send(item)} disabled={sending}>
            {item}
          </button>
        ))}
      </div>
      <InputArea sending={sending} onSend={send} />
    </section>
  );
}

function StatusTile({ icon, label, value, detail, tone = "neutral" }: { icon: ReactNode; label: string; value: string; detail?: string; tone?: "ok" | "warn" | "bad" | "neutral" }) {
  return (
    <article className={`status-tile ${tone}`}>
      <div>{icon}<span>{label}</span></div>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </article>
  );
}
