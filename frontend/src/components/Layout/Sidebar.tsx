import { Activity, Cable, Database, MessageSquare, Network, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import type { ConsoleTab } from "../../stores/systemStore";
import { useSystemStore } from "../../stores/systemStore";

const tabs: Array<{ id: ConsoleTab; label: string; icon: LucideIcon }> = [
  { id: "chat", label: "对话", icon: MessageSquare },
  { id: "memory", label: "记忆", icon: Database },
  { id: "skills", label: "技能", icon: Sparkles },
  { id: "autonomy", label: "自治", icon: Network }
];

export function Sidebar({ children }: { children: ReactNode }) {
  const { activeTab, setActiveTab, status } = useSystemStore();
  const runtimeText = status?.status === "running" ? "在线同步" : "等待连接";
  return (
    <div className="app-shell">
      <aside className="rail">
        <div className="brand"><Cable size={22} /><div><strong>冷小北</strong><span>赛博任务中枢</span></div></div>
        <nav>{tabs.map((tab) => { const Icon = tab.icon; return <button key={tab.id} className={activeTab === tab.id ? "active" : ""} onClick={() => setActiveTab(tab.id)} title={tab.label}><Icon size={18} /><span>{tab.label}</span></button>; })}</nav>
        <div className="runtime-card"><div className="runtime-title"><Activity size={16} /><span>核心链路</span></div><strong>{runtimeText}</strong><small>{status?.uptime_seconds ? `已运行 ${Math.floor(status.uptime_seconds)} 秒` : "正在扫描"}</small></div>
      </aside>
      <main className="workspace">{children}</main>
    </div>
  );
}
