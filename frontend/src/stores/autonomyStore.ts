import { create } from "zustand";
import { useSystemStore } from "./systemStore";

export type AutonomyGoal = {
  id: string;
  title: string;
  reference: string;
  objective: string;
  priority: number;
  status: string;
  attempts: number;
  next_actions?: string[];
  evidence?: unknown[];
};

export type AutonomyAuditEvent = {
  type: string;
  payload: Record<string, unknown>;
  ts: number;
};

type AutonomyState = {
  goals: AutonomyGoal[];
  run_count: number;
  last_run?: Record<string, unknown>;
  audit: AutonomyAuditEvent[];
  running?: boolean;
  loading: boolean;
  load: () => Promise<void>;
  tick: (reason?: string) => Promise<void>;
};

export const useAutonomyStore = create<AutonomyState>((set, get) => ({
  goals: [],
  run_count: 0,
  audit: [],
  loading: false,
  load: async () => {
    const apiBase = useSystemStore.getState().apiBase;
    const res = await fetch(`${apiBase}/api/autonomy/status`);
    const payload = await res.json();
    set({
      goals: payload.goals || [],
      run_count: payload.run_count || 0,
      last_run: payload.last_run || undefined,
      audit: payload.audit || [],
      running: payload.running
    });
  },
  tick: async (reason = "manual from console") => {
    const apiBase = useSystemStore.getState().apiBase;
    set({ loading: true });
    try {
      await fetch(`${apiBase}/api/autonomy/tick`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason })
      });
      await get().load();
    } finally {
      set({ loading: false });
    }
  }
}));

