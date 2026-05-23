import { FormEvent, useState } from "react";

export function SkillEditor({ onDraft }: { onDraft: (name: string, trigger: string, steps: string) => Promise<void> }) {
  const [name, setName] = useState("example_skill"); const [trigger, setTrigger] = useState("当用户提出重复任务时"); const [steps, setSteps] = useState("记录用户目标\n调用合适工具\n总结执行结果");
  async function submit(event: FormEvent) { event.preventDefault(); await onDraft(name, trigger, steps); }
  return <form className="stack" onSubmit={submit}><input value={name} onChange={(event) => setName(event.target.value)} /><input value={trigger} onChange={(event) => setTrigger(event.target.value)} /><textarea value={steps} onChange={(event) => setSteps(event.target.value)} /><button>创建 pending 技能</button></form>;
}
