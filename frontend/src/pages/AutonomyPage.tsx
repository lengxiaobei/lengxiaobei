import { Network, Play, Route, ShieldCheck } from "lucide-react";
import { useEffect } from "react";
import { useAutonomyStore } from "../stores/autonomyStore";

export function AutonomyPage() {
  const { goals, run_count, last_run, audit, loading, load, tick } = useAutonomyStore();

  useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  return (
    <section className="page autonomy-page">
      <header className="chat-header">
        <div>
          <h1>自治中枢</h1>
          <p>自主目标、网络学习、项目内执行、验证、技能进化和审计日志在这里汇合。</p>
        </div>
        <button className="ghost-button" onClick={() => tick()} disabled={loading} title="手动运行一轮自治循环">
          <Play size={16} />
          <span>{loading ? "运行中" : "运行一轮"}</span>
        </button>
      </header>

      <div className="metric-grid">
        <div><span>自治运行</span><strong>{run_count}</strong></div>
        <div><span>目标数</span><strong>{goals.length}</strong></div>
        <div><span>最近目标</span><strong className="fit-text">{String((last_run?.goal as { id?: string } | undefined)?.id || "none")}</strong></div>
      </div>

      <div className="split autonomy-split">
        <section>
          <h2><Route size={16} /> 目标路线图</h2>
          <div className="list scroll-list">
            {goals.map((goal) => (
              <article className="row" key={goal.id}>
                <div className="row-title">
                  <strong>{goal.title}</strong>
                  <span>{goal.reference}</span>
                </div>
                <p>{goal.objective}</p>
                <small>{goal.status} · attempts {goal.attempts} · priority {goal.priority}</small>
                <div className="tool-list">
                  {(goal.next_actions || []).map((action) => <span key={action}>{action}</span>)}
                </div>
              </article>
            ))}
          </div>
        </section>

        <section>
          <h2><Network size={16} /> 最近自治结果</h2>
          {last_run ? (
            <div className="list">
              <article className="row">
                <strong>{String((last_run.goal as { title?: string } | undefined)?.title || "最近目标")}</strong>
                <p>{String((last_run.goal as { objective?: string } | undefined)?.objective || "已完成一轮自治检查。")}</p>
                <small>{String(last_run.status || "completed")}</small>
              </article>
            </div>
          ) : <div className="empty">尚未运行自治循环</div>}
        </section>
      </div>

      <div className="split autonomy-split">
        <section>
          <h2><ShieldCheck size={16} /> 审计日志</h2>
          <div className="list scroll-list">
            {audit.map((event, index) => (
              <article className="row" key={`${event.type}-${event.ts}-${index}`}>
                <strong>{event.type}</strong>
                <p>{new Date(event.ts * 1000).toLocaleString()}</p>
                <small>{JSON.stringify(event.payload).slice(0, 240)}</small>
              </article>
            ))}
          </div>
        </section>
        <section>
          <h2>权限边界</h2>
          <div className="row">
            <p>冷小北可以联网学习、写项目内文件、删除项目内文件、运行项目命令、写记忆、生成 pending 技能并留下 trace。</p>
            <p>仍然禁止读写 `.env` 和项目外路径，避免把本地密钥和系统文件暴露给模型。</p>
          </div>
        </section>
      </div>
    </section>
  );
}
