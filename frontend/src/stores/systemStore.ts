import { create } from "zustand";
import { DEFAULT_API_BASE } from "../api/client";

export type ConsoleTab = "chat" | "memory" | "skills" | "autonomy" | "trace";

export type SystemStatus = {
  status: string;
  uptime_seconds?: number;
  project_root?: string;
  data_dir?: string;
  capabilities?: Array<{
    id: string;
    owner: string;
    title: string;
    description: string;
    risk: string;
    requires_confirmation: boolean;
    enabled: boolean;
  }>;
  burn?: {
    active_session?: string | null;
    total_tokens: number;
    session_count: number;
    last_session?: Record<string, unknown> | null;
  };
  model?: {
    provider: string;
    model: string;
    base_url: string;
    api_key_configured: boolean;
    fallback: string;
  };
  autonomy?: {
    run_count?: number;
    last_goal?: string;
  };
  tools?: string[];
};

type SystemStore = {
  apiBase: string;
  activeTab: ConsoleTab;
  status?: SystemStatus;
  wsConnected: boolean;
  setActiveTab: (tab: ConsoleTab) => void;
  refreshStatus: () => Promise<void>;
  applyStatus: (status: SystemStatus) => void;
  setWsConnected: (connected: boolean) => void;
};

export const useSystemStore = create<SystemStore>((set, get) => ({
  apiBase: DEFAULT_API_BASE,
  activeTab: "chat",
  wsConnected: false,
  setActiveTab: (tab) => set({ activeTab: tab }),
  applyStatus: (status) => set({ status }),
  setWsConnected: (connected) => set({ wsConnected: connected }),
  refreshStatus: async () => {
    try {
      const res = await fetch(`${get().apiBase}/api/system/status`);
      if (res.ok) {
        set({ status: await res.json() });
      }
    } catch {
      // keep last known status on fetch failure
    }
  },
}));
