import { create } from "zustand";
import { useSystemStore } from "./systemStore";

export type Skill = {
  id?: string;
  name: string;
  trigger?: string;
  status: string;
  success_count?: number;
  fail_count?: number;
  total_uses?: number;
  success_rate?: number;
  version?: number;
  source_run_id?: string;
  last_used_at?: number;
  path?: string;
  body?: Record<string, unknown>;
};

type SkillStore = {
  items: Skill[];
  loading: boolean;
  load: () => Promise<void>;
  draft: (name: string, trigger: string, steps: string) => Promise<void>;
  approve: (name: string) => Promise<void>;
  reject: (name: string) => Promise<void>;
  execute: (name: string) => Promise<unknown>;
};

export const useSkillStore = create<SkillStore>((set, get) => ({
  items: [],
  loading: false,
  load: async () => {
    const apiBase = useSystemStore.getState().apiBase;
    set({ loading: true });
    try {
      const res = await fetch(`${apiBase}/api/skills`);
      const payload = await res.json();
      set({ items: payload.items || [] });
    } finally {
      set({ loading: false });
    }
  },
  draft: async (name, trigger, steps) => {
    const apiBase = useSystemStore.getState().apiBase;
    await fetch(`${apiBase}/api/skills/draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, trigger, steps })
    });
    await get().load();
  },
  approve: async (name) => {
    const apiBase = useSystemStore.getState().apiBase;
    await fetch(`${apiBase}/api/skills/${encodeURIComponent(name)}/approve`, { method: "POST" });
    await get().load();
  },
  reject: async (name) => {
    const apiBase = useSystemStore.getState().apiBase;
    await fetch(`${apiBase}/api/skills/${encodeURIComponent(name)}/reject`, { method: "POST" });
    await get().load();
  },
  execute: async (name) => {
    const apiBase = useSystemStore.getState().apiBase;
    const res = await fetch(`${apiBase}/api/skills/${encodeURIComponent(name)}/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ inputs: {} })
    });
    const payload = await res.json();
    await get().load();
    return payload;
  }
}));
