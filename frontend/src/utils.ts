export function pct(value: number) {
  return `${Math.round(value * 100)}%`;
}

export function money(value: number) {
  return `$${value.toFixed(4)}`;
}

export function providerLabel(provider: string) {
  if (provider === "anthropic") return "Claude";
  if (provider === "openai") return "OpenAI";
  if (provider === "google") return "Gemini";
  if (provider === "openrouter") return "OpenRouter";
  if (provider === "webhook") return "BYO Agent";
  return "Mock";
}

export function topFailure(counts: Record<string, number>) {
  const [mode, count] = Object.entries(counts).sort((left, right) => right[1] - left[1])[0] ?? [];
  if (!mode) return "None";
  return `${mode.replaceAll("_", " ")} (${count})`;
}
