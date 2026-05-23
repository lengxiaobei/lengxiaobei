import { Send } from "lucide-react";
import { FormEvent, useState } from "react";

export function InputArea({ sending, onSend }: { sending: boolean; onSend: (text: string) => Promise<void> }) {
  const [text, setText] = useState("");
  async function submit(event: FormEvent) { event.preventDefault(); await onSend(text); setText(""); }
  return <form className="composer" onSubmit={submit}><input value={text} onChange={(event) => setText(event.target.value)} placeholder="输入任务或问题" /><button disabled={sending} title="发送"><Send size={18} /></button></form>;
}
