import { useState, useMemo } from "react";
import {
  ChevronDown,
  ChevronUp,
  ChevronRight,
  Wrench,
  CheckCircle2,
  XCircle,
  Loader2,
  Braces,
} from "lucide-react";
import type { ToolCall } from "../../stores/chatStore";

export function ToolCallCard({ call }: { call: ToolCall }) {
  const [open, setOpen] = useState(false);
  const [argsOpen, setArgsOpen] = useState(false);
  const [resultOpen, setResultOpen] = useState(false);

  const argsJson = useMemo(() => safeJson(call.args), [call.args]);
  const resultJson = useMemo(() => safeJson(call.result), [call.result]);
  const resultOk = call.result && !call.result.error && call.result.ok !== false;
  const isPending = !call.result;

  const summary = useMemo(() => {
    if (isPending) return "执行中...";
    if (!resultJson) return "";
    const raw = typeof call.result === "string"
      ? call.result
      : JSON.stringify(call.result);
    if (!raw) return "";
    return raw.length > 50 ? raw.slice(0, 50) + "..." : raw;
  }, [call.result, resultJson, isPending]);

  return (
    <div className="tool-call-card">
      {/* Compact summary row — click to expand/collapse */}
      <div
        className="tool-call-summary"
        onClick={() => setOpen((v) => !v)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setOpen((v) => !v); }}
      >
        <div className="tool-call-name">
          <Wrench size={13} />
          <span>{call.name}</span>
        </div>
        <div className="tool-call-status">
          {isPending ? (
            <Loader2 size={13} className="spin" />
          ) : resultOk ? (
            <CheckCircle2 size={13} className="tool-status-ok" />
          ) : (
            <XCircle size={13} className="tool-status-err" />
          )}
          {summary && <span className="tool-result-preview">{summary}</span>}
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        </div>
      </div>

      {/* Expanded details */}
      {open && (
        <>
          <div className="tool-call-header">
            <div className="tool-call-name" />
            <div className="tool-call-actions">
              {argsJson && (
                <button
                  className="tool-chunk-btn"
                  onClick={() => setArgsOpen((v) => !v)}
                  title={argsOpen ? "收起参数" : "展开参数"}
                >
                  <Braces size={11} />
                  <span>参数</span>
                  {argsOpen ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                </button>
              )}
              {resultJson && (
                <button
                  className={`tool-chunk-btn ${resultOk ? "ok" : "err"}`}
                  onClick={() => setResultOpen((v) => !v)}
                  title={resultOpen ? "收起结果" : "展开结果"}
                >
                  {resultOk ? <CheckCircle2 size={11} /> : <XCircle size={11} />}
                  <span>结果</span>
                  {resultOpen ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
                </button>
              )}
            </div>
          </div>

          {/* Args body */}
          {argsOpen && argsJson && (
            <div className="tool-chunk-body">
              <pre className="tool-json">{truncate(argsJson, 2000)}</pre>
            </div>
          )}

          {/* Result body */}
          {resultOpen && resultJson && (
            <div className="tool-chunk-body result">
              <pre className="tool-json">{truncate(resultJson, 3000)}</pre>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function safeJson(obj: unknown): string | null {
  if (obj === null || obj === undefined) return null;
  try {
    const s = JSON.stringify(obj, null, 2);
    return s.length > 2 ? s : null;
  } catch {
    return String(obj);
  }
}

function truncate(s: string, max: number): string {
  if (s.length <= max) return s;
  return s.slice(0, max) + `\n... (${s.length - max} more chars)`;
}
