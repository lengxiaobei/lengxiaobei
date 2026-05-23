import { Check, Play, Plus, X } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { useSkillStore } from "../stores/skillStore";

export function SkillsPage() {
  const { items, load, draft, approve, reject, execute } = useSkillStore();
  const [name, setName] = useState("example_skill");
  const [trigger, setTrigger] = useState("当用户提出重复任务时");
  const [steps, setSteps] = useState("记录用户目标\n调用合适工具\n总结执行结果");
  const [lastResult, setLastResult] = useState<unknown>();

  useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  async function onDraft(event: FormEvent) {
    event.preventDefault();
    await draft(name, trigger, steps);
  }

  return (
    <section className="page skills-page">
      <header>
        <h1>技能审核</h1>
        <p>Hermes 风格闭环：轨迹提炼或手动创建技能草稿，默认 pending；审核通过后才能被 Dispatcher 执行。</p>
      </header>
      <div className="split">
        <section>
          <h2>Review Queue</h2>
          <div className="list scroll-list">
            {items.length === 0 && <div className="empty">暂无技能草稿</div>}
            {items.map((skill) => (
              <article className="row" key={skill.name}>
                <strong>{skill.name}</strong>
                <p>{skill.trigger || String(skill.body?.trigger || "manual")}</p>
                <small>status: {skill.status} · success: {skill.success_count || 0} · fail: {skill.fail_count || 0}</small>
                <div className="actions">
                  <button onClick={() => approve(skill.name)}><Check size={15} /> approve</button>
                  <button onClick={() => reject(skill.name)}><X size={15} /> reject</button>
                  <button onClick={async () => setLastResult(await execute(skill.name))}><Play size={15} /> run</button>
                </div>
              </article>
            ))}
          </div>
        </section>
        <section>
          <h2>Draft Skill</h2>
          <form className="stack" onSubmit={onDraft}>
            <input value={name} onChange={(event) => setName(event.target.value)} />
            <input value={trigger} onChange={(event) => setTrigger(event.target.value)} />
            <textarea value={steps} onChange={(event) => setSteps(event.target.value)} />
            <button><Plus size={16} /> 创建 pending 技能</button>
          </form>
          <pre className="editor small-editor">{lastResult ? JSON.stringify(lastResult, null, 2) : "等待执行结果"}</pre>
        </section>
      </div>
    </section>
  );
}
