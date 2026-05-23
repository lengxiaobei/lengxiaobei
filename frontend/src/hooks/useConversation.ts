import { useChatStore } from "../stores/chatStore";

export function useConversation() {
  const { messages, sending, send } = useChatStore();
  return { messages, sending, send };
}
