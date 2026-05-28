import { useEffect, useState } from "react";
import { RefreshCw, ChevronDown, ChevronRight, CheckCircle2, AlertCircle, Clock, Zap, Wrench, Braces, FileText, Lightbulb } from "lucide-react";

const API = "/api/trace";

type Run = {
  id: string;
  user_message: string;
  channel: string;
  status: string;
  final_reply: string;
  total_tool_calls: number;
  total_steps: number;
  elapsed_ms: number;
  created_at: number;
  finished_at: number | null;
};

type ToolCall = {
  id: string;
  tool: string;
  args: Record<string, unknown>;
  result: unknown;
  error: string;
  ok: boolean;
  elapsed_ms: number;
  created_at: number;
};

type Reflection = {
  id: string;
  kind: string;
  trigger: string;
  diagnosis: string;
  lesson: string;
  skill_generated: string;
  created_at: number;
};

type FullRun = Run & {
  steps: Array<{ id: string; step_index: number; phase: string; tool_calls_count: number; elapsed_ms: number }>;
  tool_calls: ToolCall[];
  reflections: Reflection[];
};

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    completed: "var(--c-accent)",
    completed_with_errors: "#f59e0b",
    running: "#3b82f6",
    failed: "#ef4444",
  };
  const icons: Record<string, React.ReactNode> = {
    completed: <CheckCircle2 size={14} />,
    completed_with_errors: <AlertCircle size={14} />,
    running: <Clock size={14} />,
    failed: <AlertCircle size={14} />,
  };
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: colors[status] || "#888", fontSize: 12 }}>
      {icons[status] || null}
      {status}
    </span>
  );
}

function formatMs(ms: number) {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTime(ts: number) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  return d.toLocaleString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function ToolCallDetail({ tc, index }: { tc: ToolCall; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const argsStr = tc.args ? JSON.stringify(tc.args, null, 2) : "";
  const resultStr = tc.result ? JSON.stringify(tc.result, null, 2) : String(tc.result || "");

  return (
    <div style={{
      background: "var(--c-bg)", borderRadius: 6, fontSize: 12,
      borderLeft: `3px solid ${tc.ok ? "var(--c-accent)" : "#ef4444"}`,
      overflow: "hidden",
    }}>
      {/* Header row */}
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          padding: "6px 10px", display: "flex", alignItems: "center", gap: 8,
          cursor: "pointer", userSelect: "none",
        }}
      >
        <span style={{ color: "var(--c-text-muted)", minWidth: 20 }}>#{index + 1}</span>
        <Wrench size={12} style={{ opacity: 0.5 }} />
        <span style={{ fontWeight: 600 }}>{tc.tool}</span>
        <span style={{ color: "var(--c-text-muted)", marginLeft: "auto", marginRight: 8 }}>{formatMs(tc.elapsed_ms)}</span>
        {tc.ok ? <CheckCircle2 size={12} color="var(--c-accent)" /> : <AlertCircle size={12} color="#ef4444" />}
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div style={{ borderTop: "1px solid var(--c-border)", padding: "8px 10px" }}>
          {/* Args */}
          {argsStr && argsStr !== "{}" && (
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 10, color: "var(--c-text-muted)", marginBottom: 2, display: "flex", alignItems: "center", gap: 4 }}>
                <Braces size={10} /> 参数
              </div>
              <pre style={{
                background: "var(--c-surface)", borderRadius: 4, padding: "6px 8px",
                fontSize: 11, overflow: "auto", maxHeight: 200, margin: 0,
                whiteSpace: "pre-wrap", wordBreak: "break-all",
              }}>
                {argsStr.length > 1500 ? argsStr.slice(0, 1500) + "\n... (truncated)" : argsStr}
              </pre>
            </div>
          )}

          {/* Result or Error */}
          {tc.error ? (
            <div>
              <div style={{ fontSize: 10, color: "#ef4444", marginBottom: 2 }}>错误</div>
              <pre style={{
                background: "#ef444411", borderRadius: 4, padding: "6px 8px",
                fontSize: 11, overflow: "auto", maxHeight: 200, margin: 0,
                whiteSpace: "pre-wrap", wordBreak: "break-all", color: "#ef4444",
              }}>
                {tc.error}
              </pre>
            </div>
          ) : resultStr && resultStr !== "null" ? (
            <div>
              <div style={{ fontSize: 10, color: "var(--c-text-muted)", marginBottom: 2, display: "flex", alignItems: "center", gap: 4 }}>
                <FileText size={10} /> 结果
              </div>
              <pre style={{
                background: "var(--c-surface)", borderRadius: 4, padding: "6px 8px",
                fontSize: 11, overflow: "auto", maxHeight: 300, margin: 0,
                whiteSpace: "pre-wrap", wordBreak: "break-all",
              }}>
                {resultStr.length > 3000 ? resultStr.slice(0, 3000) + "\n... (truncated)" : resultStr}
              </pre>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

function RunDetail({ run, onClose }: { run: FullRun; onClose: () => void }) {
  // Deduplicate phases for the flow display
  const phaseFlow = run.steps.reduce<string[]>((acc, step) => {
    if (acc[acc.length - 1] !== step.phase) acc.push(step.phase);
    return acc;
  }, []);

  return (
    <div style={{ background: "var(--c-surface)", border: "1px solid var(--c-border)", borderRadius: 8, padding: 16, marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 14 }}>运行详情</h3>
        <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--c-text-muted)", cursor: "pointer" }}>✕</button>
      </div>

      {/* Summary */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, marginBottom: 16 }}>
        <div style={{ background: "var(--c-bg)", borderRadius: 6, padding: "8px 12px" }}>
          <div style={{ fontSize: 11, color: "var(--c-text-muted)" }}>状态</div>
          <StatusBadge status={run.status} />
        </div>
        <div style={{ background: "var(--c-bg)", borderRadius: 6, padding: "8px 12px" }}>
          <div style={{ fontSize: 11, color: "var(--c-text-muted)" }}>耗时</div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>{formatMs(run.elapsed_ms)}</div>
        </div>
        <div style={{ background: "var(--c-bg)", borderRadius: 6, padding: "8px 12px" }}>
          <div style={{ fontSize: 11, color: "var(--c-text-muted)" }}>工具调用</div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>{run.total_tool_calls}</div>
        </div>
        <div style={{ background: "var(--c-bg)", borderRadius: 6, padding: "8px 12px" }}>
          <div style={{ fontSize: 11, color: "var(--c-text-muted)" }}>迭代轮次</div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>{run.total_steps}</div>
        </div>
      </div>

      {/* User message */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: "var(--c-text-muted)", marginBottom: 4 }}>用户输入</div>
        <div style={{ background: "var(--c-bg)", borderRadius: 6, padding: "8px 12px", fontSize: 13, whiteSpace: "pre-wrap" }}>
          {run.user_message}
        </div>
      </div>

      {/* Phase flow */}
      {phaseFlow.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: "var(--c-text-muted)", marginBottom: 4 }}>阶段流转</div>
          <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
            {phaseFlow.map((phase, i) => {
              const phaseColors: Record<string, string> = {
                idle: "#6b7280",
                diagnose: "#3b82f6",
                plan: "#8b5cf6",
                execute: "#f59e0b",
                verify: "#10b981",
                reflect: "#6b7280",
              };
              const phaseLabels: Record<string, string> = {
                idle: "空闲",
                diagnose: "诊断",
                plan: "规划",
                execute: "执行",
                verify: "验证",
                reflect: "反思",
              };
              const color = phaseColors[phase] || "#6b7280";
              return (
                <div key={`${phase}-${i}`} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  {i > 0 && <span style={{ color: "var(--c-text-muted)", fontSize: 10 }}>→</span>}
                  <div style={{
                    background: `${color}22`, border: `1px solid ${color}44`, borderRadius: 4,
                    padding: "2px 8px", fontSize: 11, fontWeight: 600, color,
                  }}>
                    {phaseLabels[phase] || phase}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Tool calls timeline */}
      {run.tool_calls.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: "var(--c-text-muted)", marginBottom: 4 }}>
            工具调用链（点击展开详情）
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {run.tool_calls.map((tc, i) => (
              <ToolCallDetail key={tc.id} tc={tc} index={i} />
            ))}
          </div>
        </div>
      )}

      {/* Final reply */}
      {run.final_reply && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: "var(--c-text-muted)", marginBottom: 4 }}>最终回复</div>
          <div style={{ background: "var(--c-bg)", borderRadius: 6, padding: "8px 12px", fontSize: 13, whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto" }}>
            {run.final_reply}
          </div>
        </div>
      )}

      {/* Learnings: reflections */}
      {run.reflections.length > 0 && (
        <div>
          <div style={{ fontSize: 11, color: "var(--c-text-muted)", marginBottom: 4, display: "flex", alignItems: "center", gap: 4 }}>
            <Lightbulb size={11} /> 学习记录
          </div>
          {run.reflections.map((ref) => (
            <div key={ref.id} style={{
              background: "#f59e0b11", border: "1px solid #f59e0b33", borderRadius: 6,
              padding: "8px 12px", fontSize: 12, marginBottom: 4,
            }}>
              <div style={{ fontWeight: 600, color: "#f59e0b" }}>{ref.diagnosis}</div>
              {ref.lesson && <div style={{ color: "var(--c-text-muted)", marginTop: 4 }}>教训: {ref.lesson}</div>}
              {ref.skill_generated && <div style={{ color: "var(--c-accent)", marginTop: 4 }}>沉淀技能: {ref.skill_generated}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function TracePage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState<FullRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<Record<string, number> | null>(null);

  const fetchRuns = async () => {
    setLoading(true);
    try {
      const [runsRes, statsRes] = await Promise.all([
        fetch(`${API}/runs?limit=50`).then((r) => r.json()),
        fetch(`${API}/stats`).then((r) => r.json()),
      ]);
      setRuns(runsRes.runs || []);
      setStats(statsRes);
    } catch (e) {
      console.error("Failed to fetch traces", e);
    }
    setLoading(false);
  };

  const fetchDetail = async (runId: string) => {
    try {
      const res = await fetch(`${API}/runs/${runId}`).then((r) => r.json());
      if (!res.error) setSelected(res as FullRun);
    } catch (e) {
      console.error("Failed to fetch run detail", e);
    }
  };

  useEffect(() => {
    fetchRuns().then(() => {
      // Check if there's a pre-selected run from chat navigation
      const preSelected = sessionStorage.getItem("lengxiaobei-selected-run");
      if (preSelected) {
        sessionStorage.removeItem("lengxiaobei-selected-run");
        fetchDetail(preSelected);
      }
    });
  }, []);

  return (
    <div style={{ padding: 24, maxWidth: 900, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>执行轨迹</h2>
        <button
          onClick={fetchRuns}
          disabled={loading}
          style={{ display: "flex", alignItems: "center", gap: 4, background: "var(--c-surface)", border: "1px solid var(--c-border)", borderRadius: 6, padding: "6px 12px", cursor: "pointer", color: "var(--c-text)", fontSize: 13 }}
        >
          <RefreshCw size={14} className={loading ? "spin" : ""} />
          刷新
        </button>
      </div>

      {/* Stats bar */}
      {stats && (
        <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
          <div style={{ background: "var(--c-surface)", borderRadius: 6, padding: "8px 14px", fontSize: 13 }}>
            <Zap size={14} style={{ verticalAlign: -2, marginRight: 4 }} />
            总运行: <strong>{stats.total_runs}</strong>
          </div>
          <div style={{ background: "var(--c-surface)", borderRadius: 6, padding: "8px 14px", fontSize: 13 }}>
            成功: <strong style={{ color: "var(--c-accent)" }}>{stats.completed}</strong>
          </div>
          <div style={{ background: "var(--c-surface)", borderRadius: 6, padding: "8px 14px", fontSize: 13 }}>
            有错误: <strong style={{ color: "#f59e0b" }}>{stats.with_errors}</strong>
          </div>
          <div style={{ background: "var(--c-surface)", borderRadius: 6, padding: "8px 14px", fontSize: 13 }}>
            平均工具调用: <strong>{stats.avg_tool_calls_per_run}</strong>
          </div>
        </div>
      )}

      {/* Detail panel */}
      {selected && <RunDetail run={selected} onClose={() => setSelected(null)} />}

      {/* Run list */}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {runs.map((run) => (
          <div
            key={run.id}
            onClick={() => fetchDetail(run.id)}
            style={{
              background: selected?.id === run.id ? "var(--c-surface)" : "transparent",
              border: "1px solid var(--c-border)",
              borderRadius: 8,
              padding: "10px 14px",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 12,
              transition: "background 0.15s",
            }}
          >
            <StatusBadge status={run.status} />
            <div style={{ flex: 1, overflow: "hidden" }}>
              <div style={{ fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {run.user_message}
              </div>
              <div style={{ fontSize: 11, color: "var(--c-text-muted)", marginTop: 2 }}>
                {formatTime(run.created_at)} · {run.channel} · {run.total_tool_calls} 工具 · {formatMs(run.elapsed_ms)}
              </div>
            </div>
            {selected?.id === run.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </div>
        ))}
        {runs.length === 0 && !loading && (
          <div style={{ textAlign: "center", color: "var(--c-text-muted)", padding: 40, fontSize: 14 }}>
            暂无执行轨迹
          </div>
        )}
      </div>
    </div>
  );
}
