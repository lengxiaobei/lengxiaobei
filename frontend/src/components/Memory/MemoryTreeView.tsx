import type { MemoryNode } from "../../stores/memoryStore";

export function MemoryTreeView({ items }: { items: MemoryNode[] }) {
  return <div className="list scroll-list">{items.map((item) => <article className="row" key={item.id}><strong>{item.type}</strong><p>{item.summary || item.content}</p><small>{item.path}</small></article>)}</div>;
}
