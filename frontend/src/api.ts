import type { Provider } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? (import.meta.env.PROD ? "" : "http://localhost:8000");

export const DEFAULT_MODELS: Record<Provider, string> = {
  mock: "mock-deterministic",
  naive: "naive-scheduler",
  anthropic: "claude-sonnet-4-20250514",
  openai: "gpt-4o-mini",
  google: "gemini-2.5-flash",
  openrouter: "meta-llama/llama-3.3-70b-instruct",
  webhook: "byo-agent-webhook",
};

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || response.statusText);
  }
  return response.json();
}
