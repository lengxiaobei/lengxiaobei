type ModelSettings = {
  provider: string;
  model: string;
  base_url: string;
  api_key_configured: boolean;
  fallback: string;
};

type ModelsProps = {
  model?: ModelSettings;
};

export function Models({ model }: ModelsProps) {
  return (
    <section className="settings-panel">
      <h2>模型配置</h2>
      <div className="settings-grid">
        <label>
          Provider
          <input value={model?.provider ?? "loading"} readOnly />
        </label>
        <label>
          Model
          <input value={model?.model ?? "loading"} readOnly />
        </label>
        <label>
          Base URL
          <input value={model?.base_url ?? "loading"} readOnly />
        </label>
        <label>
          API Key
          <input value={model?.api_key_configured ? "configured" : "not configured"} readOnly />
        </label>
        <label>
          Fallback
          <input value={model?.fallback ?? "loading"} readOnly />
        </label>
        <label>
          Source
          <input value=".env / backend.config.Settings" readOnly />
        </label>
      </div>
    </section>
  );
}
