import { Activity, BrainCircuit, Cable, Database, MessageSquare, Settings, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import type { ConsoleTab } from "../../stores/systemStore";
import { useSystemStore } from "../../stores/systemStore";

const tabs: Array<{ id: ConsoleTab; label: string; icon: LucideIcon }> = [
  { id: "chat", label: "对话", icon: MessageSquare },
  { id: "memory", label: "记忆", icon: Database },
  { id: "skills", label: "技能", icon: Sparkles },
  { id: "evolution", label: "进化", icon: BrainCircuit },
  { id: "settings", label: "设置", icon: Settings }
];

export function Sidebar({ children }: { children: ReactNode }) {
  const { activeTab, setActiveTab, status } = useSystemStore();
  return (
    <div className="app-shell">
      <aside className="rail">
        <div className="brand"><Cable size={22} /><div><strong>冷小北</strong><span>Gateway</span></div></div>
        <nav>{tabs.map((tab) => { const Icon = tab.icon; return <button key={tab.id} className={activeTab === tab.id ? "active" : ""} onClick={() => setActiveTab(tab.id)} title={tab.label}><Icon size={18} /><span>{tab.label}</span></button>; })}</nav>
        <div className="runtime-card"><div className="runtime-title"><Activity size={16} /><span>运行环境</span></div><strong>{status?.status || "unknown"}</strong><small>{status?.uptime_seconds ? `${Math.floor(status.uptime_seconds)}s` : "awaiting sync"}</small></div>
      </aside>
      <main className="workspace">{children}</main>
      <aside className="side-panel"><section><h2>实时通道</h2><p>{status?.status === "running" ? "connected" : "connecting"}</p></section><section><h2>工具</h2><div className="tool-list">{(status?.tools || []).map((tool) => <span key={tool}>{tool}</span>)}</div></section></aside>
    </div>
  );
}
