export function SyncStatus({ status }: { status?: unknown }) {
  return status ? <pre className="editor small-editor">{JSON.stringify(status, null, 2)}</pre> : <div className="empty">暂无同步结果</div>;
}
