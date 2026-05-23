import { useEffect } from "react";
import { Models } from "../components/Settings/Models";
import { useSystemStore } from "../stores/systemStore";

export function SettingsPage() {
  const { apiBase, status, refreshStatus } = useSystemStore();

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  return (
    <section className="page">
      <header>
        <h1>系统设置</h1>
        <p>模型、渠道、同步源和沙箱策略在这里收敛，不再散落到脚本里。</p>
      </header>
      <div className="settings-stack">
        <Models model={status?.model} />
        <div className="settings-grid">
          <label>
            Gateway URL
            <input value={apiBase} readOnly />
          </label>
          <label>
            Default Channel
            <input value="web" readOnly />
          </label>
        </div>
      </div>
    </section>
  );
}
