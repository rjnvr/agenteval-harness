import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Clock3, Fingerprint, GitCompare, Info, KeyRound, Play, RefreshCw, Scale, Sparkles, Target, WalletCards } from "lucide-react";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE ?? (import.meta.env.PROD ? "" : "http://localhost:8000");

type Provider = "mock" | "anthropic" | "openai" | "google" | "openrouter";

type EvalRun = {
  id: number;
  mode: string;
  provider: Provider;
  model: string;
  judge_enabled: boolean;
  status: string;
  total_cases: number;
  pass_rate: number;
  avg_latency_ms: number;
  avg_cost_usd: number;
  created_at: string;
};

type EvalResult = {
  id: number;
  case_id: string;
  document_name: string;
  question: string;
  expected_answer: string;
  expected_facts: string[];
  matched_facts: string[];
  missed_facts: string[];
  expected_action: string;
  answer: string;
  action: string;
  action_input: string;
  answer_match: number;
  fact_recall: number;
  fact_precision: number;
  tool_correct: boolean;
  action_input_score: number;
  retrieval_hit: number;
  groundedness: number;
  schema_valid: boolean;
  judge_score: number | null;
  hallucination_score: number;
  unsupported_claims: string[];
  latency_ms: number;
  cost_usd: number;
  failure_type: string;
  failure_mode: string;
  failure_explanation: string;
  passed: boolean;
  retrieved_chunks: string[];
  trace: Record<string, unknown>;
};

type RunDetail = EvalRun & { results: EvalResult[] };

type Summary = {
  total_runs: number;
  total_tests_run: number;
  latest_run: EvalRun | null;
  pass_rate: number;
  avg_latency_ms: number;
  avg_cost_usd: number;
  failure_counts: Record<string, number>;
  failed_cases: EvalResult[];
  calibration: { sample_size: number; pass_agreement: number; pass_kappa: number; failure_mode_agreement: number; threshold: number };
  pii_redaction: { expected_entities: number; redacted_entities: number; recall: number };
};

type ComparisonRun = {
  id: number;
  provider: Provider;
  model: string;
  created_at: string;
  total_cases: number;
  pass_rate: number;
  avg_latency_ms: number;
  avg_cost_usd: number;
  avg_answer_match: number;
  avg_fact_recall: number;
  avg_groundedness: number;
  failure_counts: Record<string, number>;
  failed_cases: { case_id: string; failure_mode: string; answer_match: number }[];
};

type Comparison = { runs: ComparisonRun[] };

const DEFAULT_MODELS: Record<Provider, string> = {
  mock: "mock-deterministic",
  anthropic: "claude-sonnet-4-20250514",
  openai: "gpt-4o-mini",
  google: "gemini-2.5-flash",
  openrouter: "meta-llama/llama-3.3-70b-instruct",
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
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

function pct(value: number) {
  return `${Math.round(value * 100)}%`;
}

function money(value: number) {
  return `$${value.toFixed(4)}`;
}

function providerLabel(provider: string) {
  if (provider === "anthropic") return "Claude";
  if (provider === "openai") return "OpenAI";
  if (provider === "google") return "Gemini";
  if (provider === "openrouter") return "OpenRouter";
  return "Mock";
}

function MetricCard({ label, value, helper, icon }: { label: string; value: string; helper: string; icon: React.ReactNode }) {
  return (
    <section className="metric">
      <div className="metricIcon">{icon}</div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        <span>{helper}</span>
      </div>
    </section>
  );
}

function FailureBreakdown({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  if (!entries.length) return <div className="emptyBand">No failures in the latest run.</div>;
  const total = entries.reduce((sum, [, value]) => sum + value, 0);
  return (
    <div className="breakdown">
      {entries.map(([label, value]) => (
        <div className="barRow" key={label}>
          <span>{label.replaceAll("_", " ")}</span>
          <div className="barTrack"><div style={{ width: `${Math.max((value / total) * 100, 8)}%` }} /></div>
          <b>{value}</b>
        </div>
      ))}
    </div>
  );
}

function FactChips({ facts, variant }: { facts: string[]; variant: "matched" | "missed" | "unsupported" }) {
  if (!facts.length) return <p className="muted">None</p>;
  return <div className={`chips ${variant}`}>{facts.map((fact) => <span key={fact}>{fact}</span>)}</div>;
}

function ScorePill({ label, value }: { label: string; value: string }) {
  return <div className="scorePill"><span>{label}</span><b>{value}</b></div>;
}

function topFailure(counts: Record<string, number>) {
  const [mode, count] = Object.entries(counts).sort((left, right) => right[1] - left[1])[0] ?? [];
  if (!mode) return "None";
  return `${mode.replaceAll("_", " ")} (${count})`;
}

function ComparisonPanel({ runs, onSelectRun }: { runs: ComparisonRun[]; onSelectRun: (id: number) => void }) {
  if (!runs.length) {
    return (
      <section className="panel comparisonPanel">
        <div className="panelHead"><h2>LLM Comparison</h2><span>No runs yet</span></div>
        <div className="emptyBand">Run two or more model evaluations to compare results.</div>
      </section>
    );
  }
  const bestPassRate = Math.max(...runs.map((run) => run.pass_rate));
  return (
    <section className="panel comparisonPanel">
      <div className="panelHead"><h2>LLM Comparison</h2><span>{runs.length} recent runs</span></div>
      <div className="compareCards">
        {runs.slice(0, 4).map((run) => (
          <button className="compareCard" key={run.id} onClick={() => onSelectRun(run.id)}>
            <span>{providerLabel(run.provider)}</span>
            <b>{run.model}</b>
            <strong>{pct(run.pass_rate)}</strong>
            <em>{run.total_cases} cases - {Math.round(run.avg_latency_ms)} ms avg</em>
          </button>
        ))}
      </div>
      <div className="tableWrap">
        <table className="compareTable">
          <thead>
            <tr>
              <th>Run</th>
              <th>Model</th>
              <th>Pass</th>
              <th>Answer</th>
              <th>Recall</th>
              <th>Grounded</th>
              <th>Latency</th>
              <th>Cost</th>
              <th>Top Failure</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id}>
                <td><button className="textButton" onClick={() => onSelectRun(run.id)}>Run {run.id}</button><span>{new Date(run.created_at).toLocaleDateString()}</span></td>
                <td><b>{providerLabel(run.provider)}</b><span>{run.model}</span></td>
                <td><b className={run.pass_rate === bestPassRate ? "bestMetric" : ""}>{pct(run.pass_rate)}</b></td>
                <td>{pct(run.avg_answer_match)}</td>
                <td>{pct(run.avg_fact_recall)}</td>
                <td>{pct(run.avg_groundedness)}</td>
                <td>{Math.round(run.avg_latency_ms)} ms</td>
                <td>{money(run.avg_cost_usd)}</td>
                <td>{topFailure(run.failure_counts)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ResultRow({ result }: { result: EvalResult }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr>
        <td>
          <button className="iconButton" onClick={() => setOpen(!open)} aria-label={open ? "Collapse case" : "Expand case"}>
            {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </button>
        </td>
        <td><b>{result.case_id}</b><span>{result.document_name}</span></td>
        <td>{result.failure_mode.replaceAll("_", " ")}</td>
        <td>{pct(result.answer_match)}</td>
        <td>{result.tool_correct ? "Correct" : "Wrong"}</td>
        <td>{result.latency_ms} ms</td>
      </tr>
      {open && (
        <tr className="detailRow">
          <td />
          <td colSpan={5}>
            <div className="caseDetail">
              <div className="scoreGrid">
                <ScorePill label="Fact recall" value={pct(result.fact_recall)} />
                <ScorePill label="Precision" value={pct(result.fact_precision)} />
                <ScorePill label="Retrieval hit" value={pct(result.retrieval_hit)} />
                <ScorePill label="Grounded" value={pct(result.groundedness)} />
                <ScorePill label="Action input" value={pct(result.action_input_score)} />
                <ScorePill label="Schema" value={result.schema_valid ? "Valid" : "Invalid"} />
                <ScorePill label="Judge" value={result.judge_score == null ? "Off" : pct(result.judge_score)} />
              </div>
              <div><label>Question</label><p>{result.question}</p></div>
              <div><label>Expected</label><p>{result.expected_answer}</p><p className="muted">Action: {result.expected_action}</p></div>
              <div>
                <label>Agent Output</label>
                <p>{result.answer}</p>
                <p className="muted">Action: {result.action || "none"} {result.action_input ? `- ${result.action_input}` : ""}</p>
              </div>
              <div className="factGrid">
                <div><label>Matched Facts</label><FactChips facts={result.matched_facts} variant="matched" /></div>
                <div><label>Missed Facts</label><FactChips facts={result.missed_facts} variant="missed" /></div>
              </div>
              <div><label>Unsupported Claims</label><FactChips facts={result.unsupported_claims} variant="unsupported" /></div>
              <div><label>Failure Rationale</label><p>{result.failure_explanation}</p></div>
              <div>
                <label>Retrieved Context</label>
                <div className="contextList">
                  {(result.retrieved_chunks.length ? result.retrieved_chunks : ["No retrieved context."]).map((chunk, index) => (
                    <p key={`${result.id}-${index}`}>{chunk}</p>
                  ))}
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function App() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [comparison, setComparison] = useState<ComparisonRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<RunDetail | null>(null);
  const [provider, setProvider] = useState<Provider>("mock");
  const [model, setModel] = useState(DEFAULT_MODELS.mock);
  const [apiKey, setApiKey] = useState("");
  const [judgeEnabled, setJudgeEnabled] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function selectProvider(nextProvider: Provider) {
    setProvider(nextProvider);
    setModel(DEFAULT_MODELS[nextProvider]);
    if (nextProvider === "mock") setApiKey("");
  }

  async function refresh() {
    const [nextSummary, nextRuns, nextComparison] = await Promise.all([api<Summary>("/api/summary"), api<EvalRun[]>("/api/runs"), api<Comparison>("/api/comparison")]);
    setSummary(nextSummary);
    setRuns(nextRuns);
    setComparison(nextComparison.runs);
    if (nextSummary.latest_run) setSelectedRun(await api<RunDetail>(`/api/runs/${nextSummary.latest_run.id}`));
  }

  async function runEval() {
    setLoading(true);
    setError(null);
    try {
      const payload = {
        provider,
        model: model.trim() || DEFAULT_MODELS[provider],
        api_key: provider === "mock" || !apiKey.trim() ? undefined : apiKey.trim(),
        judge_enabled: judgeEnabled,
      };
      const detail = await api<RunDetail>("/api/runs", { method: "POST", body: JSON.stringify(payload) });
      setSelectedRun(detail);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh().catch((err) => setError(err instanceof Error ? err.message : "Unable to load dashboard")); }, []);

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
          </div>
          <input className="modelInput" value={model} onChange={(event) => setModel(event.target.value)} aria-label="Model name" />
          {provider !== "mock" && (
            <label className="keyField">
              <KeyRound size={15} />
              <input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={`${providerLabel(provider)} API key for this run`} aria-label="API key for this run" />
            </label>
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

      <section className="metricsGrid">
        <MetricCard label="Tests Run" value={String(summary?.total_tests_run ?? 0)} helper={`${summary?.total_runs ?? 0} total runs`} icon={<Target size={18} />} />
        <MetricCard label="Pass Rate" value={pct(summary?.pass_rate ?? 0)} helper={latestLabel} icon={<CheckCircle2 size={18} />} />
        <MetricCard label="Avg Latency" value={`${Math.round(summary?.avg_latency_ms ?? 0)} ms`} helper="Latest run average" icon={<Clock3 size={18} />} />
        <MetricCard label="Avg Cost" value={money(summary?.avg_cost_usd ?? 0)} helper="Per case estimate" icon={<WalletCards size={18} />} />
        <MetricCard label="Judge Kappa" value={(summary?.calibration?.pass_kappa ?? 0).toFixed(2)} helper={`${summary?.calibration?.sample_size ?? 0} labeled traces`} icon={<Scale size={18} />} />
        <MetricCard label="PII Recall" value={pct(summary?.pii_redaction?.recall ?? 0)} helper={`${summary?.pii_redaction?.redacted_entities ?? 0}/${summary?.pii_redaction?.expected_entities ?? 0} entities`} icon={<Fingerprint size={18} />} />
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

createRoot(document.getElementById("root")!).render(<App />);
