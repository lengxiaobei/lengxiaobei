import { MessageList } from "./MessageList";
import { InputArea } from "./InputArea";
import type { ChatMessage } from "../../stores/chatStore";

export function ChatWindow({ messages, sending, onSend }: { messages: ChatMessage[]; sending: boolean; onSend: (text: string) => Promise<void> }) {
  return <><MessageList messages={messages} /><InputArea sending={sending} onSend={onSend} /></>;
}
