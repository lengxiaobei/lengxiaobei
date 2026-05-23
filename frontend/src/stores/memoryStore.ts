import { create } from "zustand";
import { useSystemStore } from "./systemStore";

export type MemoryNode = {
  id: string;
  parent_id?: string | null;
  type: string;
  content: string;
  summary?: string;
  path?: string;
  metadata?: Record<string, unknown>;
  updated_at?: number;
};

type MemoryStore = {
  items: MemoryNode[];
  tree: MemoryNode[];
  syncStatus?: unknown;
  loading: boolean;
  search: (query: string) => Promise<void>;
  loadTree: () => Promise<void>;
  add: (content: string, type?: string, parentId?: string) => Promise<void>;
  importText: (service: string, content: string) => Promise<void>;
};

export const useMemoryStore = create<MemoryStore>((set, get) => ({
  items: [],
  tree: [],
  loading: false,
  search: async (query) => {
    const apiBase = useSystemStore.getState().apiBase;
    set({ loading: true });
    try {
      const res = await fetch(`${apiBase}/api/memory/search?q=${encodeURIComponent(query)}&limit=50`);
      const payload = await res.json();
      set({ items: payload.items || [] });
    } finally {
      set({ loading: false });
    }
  },
  loadTree: async () => {
    const apiBase = useSystemStore.getState().apiBase;
    const res = await fetch(`${apiBase}/api/memory/tree?limit=300`);
    const payload = await res.json();
    set({ tree: payload.items || [], items: payload.items || [] });
  },
  add: async (content, type = "knowledge", parentId) => {
    const apiBase = useSystemStore.getState().apiBase;
    await fetch(`${apiBase}/api/memory`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, type, parent_id: parentId || null })
    });
    await get().loadTree();
  },
  importText: async (service, content) => {
    const apiBase = useSystemStore.getState().apiBase;
    const res = await fetch(`${apiBase}/api/memory/sync/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ service, content })
    });
    const payload = await res.json();
    set({ syncStatus: payload });
    await get().loadTree();
  }
}));
