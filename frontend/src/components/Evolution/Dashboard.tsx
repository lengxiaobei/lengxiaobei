export function Dashboard({ stats }: { stats?: { skills?: { success_rate: number; count: number }, reflector?: { trace_count: number } } }) {
  return <div className="metric-grid"><div><span>技能成功率</span><strong>{Math.round((stats?.skills?.success_rate || 0) * 100)}%</strong></div><div><span>技能总数</span><strong>{stats?.skills?.count || 0}</strong></div><div><span>工具轨迹</span><strong>{stats?.reflector?.trace_count || 0}</strong></div></div>;
}
