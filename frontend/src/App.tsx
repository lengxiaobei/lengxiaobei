import { useEffect } from "react";
import { Sidebar } from "./components/Layout/Sidebar";
import { ChatPage } from "./pages/ChatPage";
import { EvolutionPage } from "./pages/EvolutionPage";
import { MemoryPage } from "./pages/MemoryPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SkillsPage } from "./pages/SkillsPage";
import { useSystemStore } from "./stores/systemStore";

export function App() {
  const { activeTab, refreshStatus } = useSystemStore();

  useEffect(() => {
    refreshStatus().catch(() => undefined);
    const id = window.setInterval(() => refreshStatus().catch(() => undefined), 5000);
    return () => window.clearInterval(id);
  }, [refreshStatus]);

  return (
    <Sidebar>
      {activeTab === "chat" && <ChatPage />}
      {activeTab === "memory" && <MemoryPage />}
      {activeTab === "skills" && <SkillsPage />}
      {activeTab === "evolution" && <EvolutionPage />}
      {activeTab === "settings" && <SettingsPage />}
    </Sidebar>
  );
}
