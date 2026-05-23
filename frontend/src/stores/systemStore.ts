import { create } from "zustand";
import { DEFAULT_API_BASE } from "../api/client";

export type ConsoleTab = "chat" | "memory" | "skills" | "evolution" | "settings";

type SystemStatus = {
  status: string;
  uptime_seconds?: number;
  project_root?: string;
  data_dir?: string;
  model?: {
    provider: string;
    model: string;
    base_url: string;
    api_key_configured: boolean;
    fallback: string;
  };
  tools?: string[];
};

type SystemStore = {
  apiBase: string;
  activeTab: ConsoleTab;
  status?: SystemStatus;
  setActiveTab: (tab: ConsoleTab) => void;
  refreshStatus: () => Promise<void>;
};

export const useSystemStore = create<SystemStore>((set, get) => ({
  apiBase: DEFAULT_API_BASE,
  activeTab: "chat",
  setActiveTab: (tab) => set({ activeTab: tab }),
  refreshStatus: async () => {
    const res = await fetch(`${get().apiBase}/api/system/status`);
    set({ status: await res.json() });
  }
}));
