import { FormEvent, useState } from "react";

export function NodeEditor({ onSave }: { onSave: (content: string) => Promise<void> }) {
  const [content, setContent] = useState("");
  async function submit(event: FormEvent) { event.preventDefault(); await onSave(content); setContent(""); }
  return <form className="stack" onSubmit={submit}><textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder="新增记忆节点" /><button>保存节点</button></form>;
}
