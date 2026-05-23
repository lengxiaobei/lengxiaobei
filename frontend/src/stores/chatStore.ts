import { create } from "zustand";
import { useSystemStore } from "./systemStore";

export type ChatMessage = {
  role: "user" | "assistant";
  text: string;
};

type ChatStore = {
  messages: ChatMessage[];
  sending: boolean;
  send: (text: string) => Promise<void>;
};

export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  sending: false,
  send: async (text) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    set({ sending: true, messages: [...get().messages, { role: "user", text: trimmed }] });
    try {
      const apiBase = useSystemStore.getState().apiBase;
      const res = await fetch(`${apiBase}/api/conversations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed, channel: "web" })
      });
      const payload = await res.json();
      const reply = payload?.result?.text || payload?.error || "没有返回内容";
      set({ messages: [...get().messages, { role: "assistant", text: reply }] });
    } finally {
      set({ sending: false });
    }
  }
}));
