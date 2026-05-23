import type { Skill } from "../../stores/skillStore";

export function SkillList({ items, onApprove, onReject, onRun }: { items: Skill[]; onApprove: (name: string) => void; onReject: (name: string) => void; onRun: (name: string) => void }) {
  return <div className="list scroll-list">{items.length === 0 && <div className="empty">暂无技能草稿</div>}{items.map((skill) => <article className="row" key={skill.name}><strong>{skill.name}</strong><p>{skill.trigger || String(skill.body?.trigger || "manual")}</p><small>status: {skill.status} · success: {skill.success_count || 0} · fail: {skill.fail_count || 0}</small><div className="actions"><button onClick={() => onApprove(skill.name)}>approve</button><button onClick={() => onReject(skill.name)}>reject</button><button onClick={() => onRun(skill.name)}>run</button></div></article>)}</div>;
}
