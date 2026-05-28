import { Check, Play, Plus, X, TrendingDown, TrendingUp, AlertTriangle, ExternalLink } from "lucide-react";
import { FormEvent, useEffect, useState, useCallback } from "react";
import { useSkillStore } from "../stores/skillStore";
import { useSystemStore } from "../stores/systemStore";

interface FailurePattern {
  id: string;
  pattern: string;
  tool: string;
  error_signature: string;
  occurrence_count: number;
  first_seen_at: number;
  last_seen_at: number;
  resolved: number;
  resolution?: string;
}

export function SkillsPage() {
  const { items, load, draft, approve, reject, execute } = useSkillStore();
  const setActiveTab = useSystemStore((s) => s.setActiveTab);
  const [name, setName] = useState("example_skill");
  const [trigger, setTrigger] = useState("当用户提出重复任务时");
  const [steps, setSteps] = useState("记录用户目标\n调用合适工具\n总结执行结果");
  const [lastResult, setLastResult] = useState<unknown>();
  const [failurePatterns, setFailurePatterns] = useState<FailurePattern[]>([]);
  const [showPatterns, setShowPatterns] = useState(false);
  const [demoting, setDemoting] = useState(false);

  useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  const loadFailurePatterns = useCallback(async () => {
    try {
      const resp = await fetch("/api/skills/failure-patterns?min_occurrences=1");
      const data = await resp.json();
      setFailurePatterns(data.items || []);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (showPatterns) loadFailurePatterns();
  }, [showPatterns, loadFailurePatterns]);

  async function onDraft(event: FormEvent) {
    event.preventDefault();
    await draft(name, trigger, steps);
  }

  async function onAutoDemote() {
    setDemoting(true);
    try {
      const resp = await fetch("/api/skills/auto-demote", { method: "POST" });
      const data = await resp.json();
      if (data.count > 0) {
        alert(`已降权 ${data.count} 个低质量技能: ${data.demoted.join(", ")}`);
      } else {
        alert("没有需要降权的技能");
      }
      await load();
    } catch {
      alert("降权操作失败");
    }
    setDemoting(false);
  }

  function viewTrace(runId: string) {
    sessionStorage.setItem("lengxiaobei-selected-run", runId);
    setActiveTab("trace" as any);
  }

  const successRateColor = (rate: number) => {
    if (rate >= 70) return "text-green";
    if (rate >= 40) return "text-yellow";
    return "text-red";
  };

  return (
    <section className="page skills-page">
      <header>
        <h1>技能管理</h1>
        <p>冷小北的技能库：自动生成的技能经过审核后才能被使用，系统会自动降权低质量技能。</p>
      </header>
      <div className="split">
        <section>
          <div className="flex-between" style={{ marginBottom: 12 }}>
            <h2>技能列表</h2>
            <div className="flex gap-8">
              <button className="btn-sm" onClick={() => setShowPatterns(!showPatterns)}>
                <AlertTriangle size={14} /> 失败模式 {failurePatterns.length > 0 && `(${failurePatterns.length})`}
              </button>
              <button className="btn-sm" onClick={onAutoDemote} disabled={demoting}>
                <TrendingDown size={14} /> {demoting ? "降权中..." : "自动降权"}
              </button>
            </div>
          </div>

          {/* Failure Patterns Panel */}
          {showPatterns && (
            <div className="panel" style={{ marginBottom: 16 }}>
              <h3>失败模式库</h3>
              {failurePatterns.length === 0 ? (
                <div className="empty">暂无失败模式记录</div>
              ) : (
                <div className="list scroll-list" style={{ maxHeight: 200 }}>
                  {failurePatterns.map((p) => (
                    <div key={p.id} className="row" style={{ padding: 8 }}>
                      <div className="flex-between">
                        <strong style={{ fontSize: 13 }}>{p.tool}</strong>
                        <span className="badge">{p.occurrence_count}次</span>
                      </div>
                      <p style={{ margin: "4px 0", fontSize: 12, opacity: 0.7 }}>{p.error_signature}</p>
                      <small style={{ opacity: 0.5 }}>
                        最后出现: {new Date(p.last_seen_at * 1000).toLocaleString()}
                      </small>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="list scroll-list">
            {items.length === 0 && <div className="empty">暂无技能</div>}
            {items.map((skill) => (
              <article className="row" key={skill.name}>
                <div className="flex-between">
                  <strong>{skill.name}</strong>
                  <div className="flex gap-6">
                    {(skill.version ?? 0) > 1 && <span className="badge">v{skill.version}</span>}
                    <span className={`badge ${successRateColor(skill.success_rate || 0)}`}>
                      {skill.success_rate || 0}%
                    </span>
                    <span className={`badge badge-${skill.status}`}>{skill.status}</span>
                  </div>
                </div>
                <p style={{ margin: "4px 0", fontSize: 13 }}>{skill.trigger || String(skill.body?.trigger || "manual")}</p>
                <div className="flex-between" style={{ fontSize: 12, opacity: 0.6 }}>
                  <span>
                    使用: {skill.total_uses || 0}次 · 成功: {skill.success_count || 0} · 失败: {skill.fail_count || 0}
                  </span>
                  {skill.source_run_id ? (
                    <button className="link-btn" onClick={() => viewTrace(String(skill.source_run_id))}>
                      <ExternalLink size={12} /> 来源轨迹
                    </button>
                  ) : null}
                </div>
                <div className="actions">
                  {skill.status === "pending" && (
                    <>
                      <button onClick={() => approve(skill.name)}><Check size={15} /> 通过</button>
                      <button onClick={() => reject(skill.name)}><X size={15} /> 拒绝</button>
                    </>
                  )}
                  <button onClick={async () => setLastResult(await execute(skill.name))}><Play size={15} /> 运行</button>
                </div>
              </article>
            ))}
          </div>
        </section>
        <section>
          <h2>新建技能草稿</h2>
          <form className="stack" onSubmit={onDraft}>
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="技能名称" />
            <input value={trigger} onChange={(event) => setTrigger(event.target.value)} placeholder="触发条件" />
            <textarea value={steps} onChange={(event) => setSteps(event.target.value)} placeholder="执行步骤（每行一步）" />
            <button><Plus size={16} /> 创建 pending 技能</button>
          </form>
          <pre className="editor small-editor">{lastResult ? JSON.stringify(lastResult, null, 2) : "等待执行结果"}</pre>
        </section>
      </div>
    </section>
  );
}
