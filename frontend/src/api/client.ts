export const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${DEFAULT_API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {})
    }
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}
