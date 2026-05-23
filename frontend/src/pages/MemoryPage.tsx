import { Database, Plus, Search, UploadCloud } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { useMemoryStore } from "../stores/memoryStore";

export function MemoryPage() {
  const [query, setQuery] = useState("");
  const [content, setContent] = useState("");
  const [service, setService] = useState("manual");
  const { items, tree, loading, syncStatus, search, loadTree, add, importText } = useMemoryStore();

  useEffect(() => {
    loadTree().catch(() => undefined);
  }, [loadTree]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    await search(query);
  }

  async function onAdd(event: FormEvent) {
    event.preventDefault();
    await add(content, "knowledge");
    setContent("");
  }

  async function onImport(event: FormEvent) {
    event.preventDefault();
    await importText(service, content);
    setContent("");
  }

  return (
    <section className="page memory-page">
      <header>
        <h1>记忆树</h1>
        <p>OpenHuman 风格的本地可编辑记忆树：节点 CRUD、树查询、搜索、同步导入和图谱边都走后端真实 API。</p>
      </header>
      <div className="split">
        <section>
          <h2><Search size={16} /> 搜索 / 树</h2>
          <form className="search-bar" onSubmit={onSubmit}>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索记忆节点" />
            <button title="搜索"><Search size={18} /></button>
          </form>
          <button className="secondary" onClick={() => loadTree()}><Database size={16} /> 载入记忆树 ({tree.length})</button>
          <div className="list scroll-list">
            {loading && <div className="empty">加载中...</div>}
            {items.map((item) => (
              <article className="row" key={item.id}>
                <strong>{item.type}</strong>
                <p>{item.summary || item.content}</p>
                <small>{item.path}</small>
              </article>
            ))}
          </div>
        </section>
        <section>
          <h2><Plus size={16} /> 新增 / 同步导入</h2>
          <form className="stack" onSubmit={onAdd}>
            <textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder="写入一条知识，或粘贴要同步导入的 HTML/文本" />
            <button><Plus size={16} /> 写入 knowledge 节点</button>
          </form>
          <form className="stack" onSubmit={onImport}>
            <input value={service} onChange={(event) => setService(event.target.value)} placeholder="同步源名称，如 gmail/notion/manual" />
            <button><UploadCloud size={16} /> 作为同步源导入</button>
          </form>
          {syncStatus ? <pre className="editor small-editor">{JSON.stringify(syncStatus, null, 2)}</pre> : null}
        </section>
      </div>
    </section>
  );
}
