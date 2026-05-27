export const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE || "";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body: string = "",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${DEFAULT_API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  const raw = await res.text();
  if (!res.ok) {
    let message = `API ${res.status}`;
    try {
      const payload = JSON.parse(raw);
      message = payload?.detail || payload?.error || payload?.message || message;
    } catch {}
    throw new ApiError(res.status, message, raw);
  }
  if (!raw.trim()) {
    throw new ApiError(res.status, "API returned an empty response", raw);
  }
  return JSON.parse(raw) as T;
}
