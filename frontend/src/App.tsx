import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Clock3, Fingerprint, Info, KeyRound, Link as LinkIcon, Play, RefreshCw, Scale, Sparkles, Target, WalletCards } from "lucide-react";
import { api, DEFAULT_MODELS } from "./api";
import { ComparisonPanel } from "./components/ComparisonPanel";
import { FailureBreakdown } from "./components/FailureBreakdown";
import { MetricCard } from "./components/MetricCard";
import { QualitySignal } from "./components/QualitySignal";
import { ResultRow } from "./components/ResultRow";
import type { Comparison, ComparisonRun, EvalRun, EvalSummary, Provider, RunDetail, Summary } from "./types";
import { money, pct, providerLabel } from "./utils";

function parseWebhookHeaders(raw: string): Record<string, string> | undefined {
  const trimmed = raw.trim();
  if (!trimmed) return undefined;
  try {
    const parsed = JSON.parse(trimmed);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      const out: Record<string, string> = {};
      for (const [key, value] of Object.entries(parsed)) {
        if (typeof value === "string") out[key] = value;
      }
      return Object.keys(out).length ? out : undefined;
    }
  } catch {
    const out: Record<string, string> = {};
    for (const line of trimmed.split(/\r?\n/)) {
      const idx = line.indexOf(":");
      if (idx === -1) continue;
      const key = line.slice(0, idx).trim();
      const value = line.slice(idx + 1).trim();
      if (key) out[key] = value;
    }
    return Object.keys(out).length ? out : undefined;
  }
  return undefined;
}

export function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [comparison, setComparison] = useState<ComparisonRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<RunDetail | null>(null);
  const [provider, setProvider] = useState<Provider>("mock");
  const [model, setModel] = useState(DEFAULT_MODELS.mock);
  const [apiKey, setApiKey] = useState("");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [webhookHeaders, setWebhookHeaders] = useState("");
  const [judgeEnabled, setJudgeEnabled] = useState(false);
  const [loading, setLoading] = useState(false);
  const [runProgress, setRunProgress] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [evalSummary, setEvalSummary] = useState<EvalSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  function selectProvider(nextProvider: Provider) {
    setProvider(nextProvider);
    setModel(DEFAULT_MODELS[nextProvider]);
    if (nextProvider === "mock") setApiKey("");
  }

  const refresh = useCallback(async () => {
    const [nextSummary, nextRuns, nextComparison] = await Promise.all([api<Summary>("/api/summary"), api<EvalRun[]>("/api/runs"), api<Comparison>("/api/comparison")]);
    setSummary(nextSummary);
    setRuns(nextRuns);
    setComparison(nextComparison.runs);
    if (nextSummary.latest_run) setSelectedRun(await api<RunDetail>(`/api/runs/${nextSummary.latest_run.id}`));
  }, []);

  async function runEval() {
    setLoading(true);
    setRunProgress(null);
    setError(null);
    try {
      if (provider === "webhook" && !webhookUrl.trim()) {
        throw new Error("Enter a webhook URL for your agent.");
      }
      const payload = {
        provider,
        model: model.trim() || DEFAULT_MODELS[provider],
        api_key: provider === "mock" || provider === "webhook" || !apiKey.trim() ? undefined : apiKey.trim(),
        judge_enabled: provider === "webhook" ? false : judgeEnabled,
        async_run: true,
        webhook_url: provider === "webhook" ? webhookUrl.trim() : undefined,
        webhook_headers: provider === "webhook" ? parseWebhookHeaders(webhookHeaders) : undefined,
      };
      let detail = await api<RunDetail>("/api/runs", { method: "POST", body: JSON.stringify(payload) });
      setSelectedRun(detail);
      setRunProgress(`Run ${detail.id} queued`);
      while (detail.status === "queued" || detail.status === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 900));
        detail = await api<RunDetail>(`/api/runs/${detail.id}/status`);
        setSelectedRun(detail);
        setRunProgress(`Run ${detail.id} ${detail.status} - ${detail.results.length}/${detail.total_cases} cases`);
      }
      if (detail.status === "failed") throw new Error(`Run ${detail.id} failed.`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed");
    } finally {
      setLoading(false);
      setRunProgress(null);
    }
  }

  async function summarizeLatestRun() {
    setSummaryLoading(true);
    setError(null);
    try {
      const payload = {
        provider,
        model: model.trim() || DEFAULT_MODELS[provider],
        api_key: provider === "mock" || !apiKey.trim() ? undefined : apiKey.trim(),
      };
      const nextSummary = await api<EvalSummary>("/api/runs/latest/summary", { method: "POST", body: JSON.stringify(payload) });
      setEvalSummary(nextSummary);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Summary failed");
    } finally {
      setSummaryLoading(false);
    }
  }

  useEffect(() => { refresh().catch((err) => setError(err instanceof Error ? err.message : "Unable to load dashboard")); }, [refresh]);

  const failed = selectedRun?.results.filter((result) => !result.passed) ?? summary?.failed_cases ?? [];
  const latestLabel = useMemo(() => {
    if (!summary?.latest_run) return "No runs yet";
    return `Run ${summary.latest_run.id} - ${providerLabel(summary.latest_run.provider)} - ${new Date(summary.latest_run.created_at).toLocaleString()}`;
  }, [summary]);

  return (
    <main>
      <header className="topbar">
        <div>
          <h1>AgentEval Harness</h1>
          <p>Evaluation dashboard for RAG and tool-using document agents.</p>
        </div>
        <div className="controls">
          <div className="segmented" aria-label="Provider">
            <button className={provider === "mock" ? "active" : ""} onClick={() => selectProvider("mock")}>Mock</button>
            <button className={provider === "anthropic" ? "active" : ""} onClick={() => selectProvider("anthropic")}>Claude</button>
            <button className={provider === "openai" ? "active" : ""} onClick={() => selectProvider("openai")}>OpenAI</button>
            <button className={provider === "google" ? "active" : ""} onClick={() => selectProvider("google")}>Gemini</button>
            <button className={provider === "openrouter" ? "active" : ""} onClick={() => selectProvider("openrouter")}>Llama</button>
            <button className={provider === "webhook" ? "active" : ""} onClick={() => selectProvider("webhook")}>BYO Agent</button>
          </div>
          <input className="modelInput" value={model} onChange={(event) => setModel(event.target.value)} aria-label="Model name" />
          {provider !== "mock" && provider !== "webhook" && (
            <label className="keyField">
              <KeyRound size={15} />
              <input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={`${providerLabel(provider)} API key for this run`} aria-label="API key for this run" />
            </label>
          )}
          {provider === "webhook" && (
            <>
              <label className="keyField">
                <LinkIcon size={15} />
                <input
                  type="url"
                  value={webhookUrl}
                  onChange={(event) => setWebhookUrl(event.target.value)}
                  placeholder="https://your-agent.example.com/run"
                  aria-label="Webhook URL for your agent"
                />
              </label>
              <label className="keyField" title='Optional: JSON object or "Header: value" lines'>
                <KeyRound size={15} />
                <input
                  type="text"
                  value={webhookHeaders}
                  onChange={(event) => setWebhookHeaders(event.target.value)}
                  placeholder='Headers (optional) e.g. {"Authorization":"Bearer ..."}'
                  aria-label="Webhook headers"
                />
              </label>
            </>
          )}
          <div className={`judgeControl ${judgeEnabled ? "active" : ""}`}>
            <label className="judgeToggle">
              <input type="checkbox" checked={judgeEnabled} onChange={(event) => setJudgeEnabled(event.target.checked)} />
              <span className="judgeIcon"><Sparkles size={18} /></span>
              <span><b>LLM Judge</b><em>{judgeEnabled ? "Enabled" : "Off"}</em></span>
            </label>
            <button className="judgeInfo" type="button" aria-label="What LLM Judge does">
              <Info size={17} />
              <span className="judgePopup" role="tooltip">
                Runs an extra model call to score semantic correctness against the expected answer. It helps catch fuzzy answer quality, but can add latency and provider cost.
              </span>
            </button>
          </div>
          <button className="secondary" onClick={() => refresh()} title="Refresh dashboard"><RefreshCw size={16} /></button>
          <button className="primary" onClick={runEval} disabled={loading}><Play size={16} />{loading ? "Running" : "Run evals"}</button>
        </div>
      </header>

      {error && <div className="error"><AlertTriangle size={16} />{error}</div>}
      {runProgress && <div className="runProgress"><RefreshCw size={16} />{runProgress}</div>}

      <section className="metricsGrid">
        <MetricCard label="Tests Run" value={String(summary?.total_tests_run ?? 0)} helper={`${summary?.total_runs ?? 0} total runs`} icon={<Target size={18} />} />
        <MetricCard label="Strict Pass Rate" value={pct(summary?.pass_rate ?? 0)} helper={latestLabel} icon={<CheckCircle2 size={18} />} />
        <MetricCard label="Avg Latency" value={`${Math.round(summary?.avg_latency_ms ?? 0)} ms`} helper="Latest run average" icon={<Clock3 size={18} />} />
        <MetricCard label="Avg Cost" value={money(summary?.avg_cost_usd ?? 0)} helper="Per case estimate" icon={<WalletCards size={18} />} />
        <MetricCard label="Judge Kappa" value={(summary?.calibration?.pass_kappa ?? 0).toFixed(2)} helper={`${summary?.calibration?.sample_size ?? 0} labeled traces`} icon={<Scale size={18} />} />
        <MetricCard label="PII Recall" value={pct(summary?.pii_redaction?.recall ?? 0)} helper={`${summary?.pii_redaction?.redacted_entities ?? 0}/${summary?.pii_redaction?.expected_entities ?? 0} entities`} icon={<Fingerprint size={18} />} />
      </section>

      <section className="qualityPanel">
        <div>
          <span className="eyebrow">Score Breakdown</span>
          <h2>Latest run quality signals</h2>
        </div>
        <div className="qualityGrid">
          <QualitySignal label="Answer quality" value={summary?.score_breakdown?.semantic_quality ?? 0} helper="Semantic match or judge score" />
          <QualitySignal label="Fact completeness" value={summary?.score_breakdown?.fact_completeness ?? 0} helper="Required facts included" />
          <QualitySignal label="Tool accuracy" value={summary?.score_breakdown?.tool_accuracy ?? 0} helper="Action and arguments" />
          <QualitySignal label="Grounding" value={summary?.score_breakdown?.grounding ?? 0} helper="Supported by context" />
          <QualitySignal label="Retrieval" value={summary?.score_breakdown?.retrieval_quality ?? 0} helper="Expected facts retrieved" />
        </div>
      </section>

      <section className="summaryWidget">
        <div>
          <span className="eyebrow">Latest Run Summary</span>
          <h2>Explain the eval results</h2>
          <p>Generate a concise readout of the latest run, including what passed, what failed, failure patterns, and next steps.</p>
        </div>
        <button className="summaryButton" onClick={summarizeLatestRun} disabled={summaryLoading || !summary?.latest_run}>
          <Sparkles size={17} />{summaryLoading ? "Summarizing" : "Summarize latest run"}
        </button>
        {evalSummary && (
          <div className="summaryOutput">
            <label>Run {evalSummary.run_id} - {providerLabel(evalSummary.provider)} - {evalSummary.model}</label>
            {evalSummary.summary.split("\n").filter(Boolean).map((line, index) => (
              <p key={`${evalSummary.run_id}-${index}`}>{line}</p>
            ))}
          </div>
        )}
      </section>

      <div className="dashboardBand">
        <ComparisonPanel runs={comparison} onSelectRun={async (id) => setSelectedRun(await api<RunDetail>(`/api/runs/${id}`))} />
      </div>

      <section className="contentGrid">
        <div className="panel">
          <div className="panelHead"><h2>Failed Cases</h2><span>{failed.length} failing</span></div>
          <div className="tableWrap">
            <table>
              <thead><tr><th /><th>Case</th><th>Failure</th><th>Answer</th><th>Tool</th><th>Latency</th></tr></thead>
              <tbody>
                {failed.length ? failed.map((result) => <ResultRow key={result.id} result={result} />) : (
                  <tr><td colSpan={6} className="emptyCell">Run the suite to inspect failures.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <aside className="sideStack">
          <div className="panel"><div className="panelHead"><h2>Failure Types</h2></div><FailureBreakdown counts={summary?.failure_counts ?? {}} /></div>
          <div className="panel">
            <div className="panelHead"><h2>Recent Runs</h2></div>
            <div className="runList">
              {runs.map((run) => (
                <button key={run.id} onClick={async () => setSelectedRun(await api<RunDetail>(`/api/runs/${run.id}`))}>
                  <b>Run {run.id}</b>
                  <span>{providerLabel(run.provider)} - {run.model} - {pct(run.pass_rate)} - {run.total_cases} cases</span>
                </button>
              ))}
              {!runs.length && <div className="emptyBand">No eval runs yet.</div>}
            </div>
          </div>
        </aside>
      </section>
    </main>
  );
}
