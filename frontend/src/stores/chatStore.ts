import { create } from "zustand";
import { apiJson } from "../api/client";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  createdAt: number;
};

type ChatStore = {
  messages: ChatMessage[];
  sending: boolean;
  send: (text: string) => Promise<void>;
  clear: () => void;
};

function makeMessage(role: ChatMessage["role"], text: string): ChatMessage {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    text,
    createdAt: Date.now(),
  };
}

type ConversationResponse = {
  status: string;
  result: { text: string };
};

// ── Persistence ─────────────────────────────────────────────────
const STORAGE_KEY = "lengxiaobei-chat-messages";
const MAX_PERSISTED = 100;

function loadMessages(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.slice(-MAX_PERSISTED) : [];
  } catch {
    return [];
  }
}

function saveMessages(messages: ChatMessage[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-MAX_PERSISTED)));
  } catch {
    // quota exceeded or private browsing — silently skip
  }
}

export const useChatStore = create<ChatStore>((set, get) => ({
  messages: loadMessages(),
  sending: false,
  send: async (text) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const newMessages = [...get().messages, makeMessage("user", trimmed)];
    set({ sending: true, messages: newMessages });
    saveMessages(newMessages);
    try {
      const payload = await apiJson<ConversationResponse>("/api/conversations", {
        method: "POST",
        body: JSON.stringify({ message: trimmed, channel: "web" }),
      });
      const updated = [...get().messages, makeMessage("assistant", payload?.result?.text || "没有返回内容")];
      set({ messages: updated });
      saveMessages(updated);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "请求失败";
      const updated = [...get().messages, makeMessage("assistant", `连接失败：${errorMessage}`)];
      set({ messages: updated });
      saveMessages(updated);
    } finally {
      set({ sending: false });
    }
  },
  clear: () => {
    set({ messages: [] });
    saveMessages([]);
  },
}));
