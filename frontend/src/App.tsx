import { useCallback, useEffect, useRef } from "react";
import { Sidebar } from "./components/Layout/Sidebar";
import { ChatPage } from "./pages/ChatPage";
import { AutonomyPage } from "./pages/AutonomyPage";
import { MemoryPage } from "./pages/MemoryPage";
import { SkillsPage } from "./pages/SkillsPage";
import { TracePage } from "./pages/TracePage";
import { useSystemStore, type SystemStatus } from "./stores/systemStore";
import { useWebSocket } from "./hooks/useWebSocket";

export function App() {
  const { activeTab, setActiveTab, refreshStatus, applyStatus, setWsConnected } = useSystemStore();
  const hasFetched = useRef(false);

  // Listen for trace navigation events from chat messages
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.runId) {
        setActiveTab("trace");
        // Store the runId for TracePage to pick up
        sessionStorage.setItem("lengxiaobei-selected-run", detail.runId);
      }
    };
    window.addEventListener("lengxiaobei:show-trace", handler);
    return () => window.removeEventListener("lengxiaobei:show-trace", handler);
  }, [setActiveTab]);

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
      {activeTab === "trace" && <TracePage />}
    </Sidebar>
  );
}
