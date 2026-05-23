import { create } from "zustand";
import { useSystemStore } from "./systemStore";

export type ToolTrace = {
  id?: string;
  tool: string;
  ok: boolean;
  args?: Record<string, unknown>;
  result?: unknown;
  error?: string;
  elapsed_ms?: number;
  created_at?: number;
};

type EvolutionStats = {
  skills?: { count: number; by_status: Record<string, number>; success_rate: number };
  reflector?: { trace_count: number; success_count: number; fail_count: number; last_reflection?: unknown };
  tools?: Array<{ name: string; callable: string }>;
};

type EvolutionStore = {
  traces: ToolTrace[];
  stats?: EvolutionStats;
  lastReflection?: unknown;
  load: () => Promise<void>;
  reflect: (topic: string) => Promise<void>;
};

export const useEvolutionStore = create<EvolutionStore>((set, get) => ({
  traces: [],
  load: async () => {
    const apiBase = useSystemStore.getState().apiBase;
    const [statsRes, traceRes] = await Promise.all([
      fetch(`${apiBase}/api/evolution/stats`),
      fetch(`${apiBase}/api/evolution/traces?limit=30`)
    ]);
    set({ stats: await statsRes.json(), traces: (await traceRes.json()).items || [] });
  },
  reflect: async (topic) => {
    const apiBase = useSystemStore.getState().apiBase;
    const res = await fetch(`${apiBase}/api/evolution/reflect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, force_skill: true })
    });
    set({ lastReflection: await res.json() });
    await get().load();
  }
}));
