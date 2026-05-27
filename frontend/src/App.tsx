import { useCallback, useEffect, useRef } from "react";
import { Sidebar } from "./components/Layout/Sidebar";
import { ChatPage } from "./pages/ChatPage";
import { AutonomyPage } from "./pages/AutonomyPage";
import { MemoryPage } from "./pages/MemoryPage";
import { SkillsPage } from "./pages/SkillsPage";
import { useSystemStore, type SystemStatus } from "./stores/systemStore";
import { useWebSocket } from "./hooks/useWebSocket";

export function App() {
  const { activeTab, refreshStatus, applyStatus, setWsConnected } = useSystemStore();
  const hasFetched = useRef(false);

  // Initial fetch on mount
  useEffect(() => {
    if (hasFetched.current) return;
    hasFetched.current = true;
    refreshStatus().catch(() => {});
  }, [refreshStatus]);

  const onWsMessage = useCallback(
    (data: unknown) => {
      const payload = data as Record<string, unknown> | null;
      if (!payload) return;
      switch (payload.type) {
        case "system.connected":
          setWsConnected(true);
          if (payload.payload) applyStatus(payload.payload as SystemStatus);
          break;
        case "system.status":
          if (payload.payload) applyStatus(payload.payload as SystemStatus);
          break;
      }
    },
    [applyStatus, setWsConnected],
  );

  const { connected } = useWebSocket(onWsMessage);

  // Poll as fallback when WS is disconnected (every 30s instead of 5s)
  useEffect(() => {
    if (connected) return;
    const id = window.setInterval(() => refreshStatus().catch(() => {}), 30_000);
    return () => window.clearInterval(id);
  }, [connected, refreshStatus]);

  return (
    <Sidebar>
      {activeTab === "chat" && <ChatPage />}
      {activeTab === "memory" && <MemoryPage />}
      {activeTab === "skills" && <SkillsPage />}
      {activeTab === "autonomy" && <AutonomyPage />}
    </Sidebar>
  );
}
