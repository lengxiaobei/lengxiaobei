import { BrainCircuit, RefreshCw } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { useEvolutionStore } from "../stores/evolutionStore";

export function EvolutionPage() {
  const { stats, traces, lastReflection, load, reflect } = useEvolutionStore();
  const [topic, setTopic] = useState("从最近工具轨迹提炼可复用技能");

  useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  async function onReflect(event: FormEvent) {
    event.preventDefault();
    await reflect(topic);
  }

  return (
    <section className="page evolution-page">
      <header>
        <h1>进化闭环</h1>
        <p>Hermes 风格：Dispatcher 持久化 trace，Reflector 从成功轨迹提炼 pending 技能，Evaluator 统计成功率。</p>
      </header>
      <div className="metric-grid">
        <div><span>技能成功率</span><strong>{Math.round((stats?.skills?.success_rate || 0) * 100)}%</strong></div>
        <div><span>技能总数</span><strong>{stats?.skills?.count || 0}</strong></div>
        <div><span>工具轨迹</span><strong>{stats?.reflector?.trace_count || traces.length}</strong></div>
      </div>
      <div className="split">
        <section>
          <h2><BrainCircuit size={16} /> 触发反思</h2>
          <form className="stack" onSubmit={onReflect}>
            <input value={topic} onChange={(event) => setTopic(event.target.value)} />
            <button><RefreshCw size={16} /> 从轨迹生成技能草稿</button>
          </form>
          <pre className="editor small-editor">{lastReflection ? JSON.stringify(lastReflection, null, 2) : "尚未触发反思"}</pre>
        </section>
        <section>
          <h2>Recent Tool Traces</h2>
          <div className="list scroll-list">
            {traces.map((trace, index) => (
              <article className="row" key={trace.id || index}>
                <strong>{trace.tool}</strong>
                <p>{trace.ok ? "ok" : trace.error}</p>
                <small>{trace.elapsed_ms || 0}ms</small>
              </article>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}
