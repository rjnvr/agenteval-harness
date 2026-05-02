import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Clock3, Play, RefreshCw, Target, WalletCards } from "lucide-react";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

type EvalRun = {
  id: number;
  mode: string;
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
  expected_action: string;
  answer: string;
  action: string;
  action_input: string;
  answer_match: number;
  tool_correct: boolean;
  hallucination_score: number;
  latency_ms: number;
  cost_usd: number;
  failure_type: string;
  passed: boolean;
  retrieved_chunks: string[];
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
  if (!entries.length) {
    return <div className="emptyBand">No failures in the latest run.</div>;
  }
  const total = entries.reduce((sum, [, value]) => sum + value, 0);
  return (
    <div className="breakdown">
      {entries.map(([label, value]) => (
        <div className="barRow" key={label}>
          <span>{label.replaceAll("_", " ")}</span>
          <div className="barTrack">
            <div style={{ width: `${Math.max((value / total) * 100, 8)}%` }} />
          </div>
          <b>{value}</b>
        </div>
      ))}
    </div>
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
        <td>
          <b>{result.case_id}</b>
          <span>{result.document_name}</span>
        </td>
        <td>{result.failure_type.replaceAll("_", " ")}</td>
        <td>{pct(result.answer_match)}</td>
        <td>{result.tool_correct ? "Correct" : "Wrong"}</td>
        <td>{result.latency_ms} ms</td>
      </tr>
      {open && (
        <tr className="detailRow">
          <td />
          <td colSpan={5}>
            <div className="caseDetail">
              <div>
                <label>Question</label>
                <p>{result.question}</p>
              </div>
              <div>
                <label>Expected</label>
                <p>{result.expected_answer}</p>
                <p className="muted">Action: {result.expected_action}</p>
              </div>
              <div>
                <label>Agent Output</label>
                <p>{result.answer}</p>
                <p className="muted">Action: {result.action || "none"} {result.action_input ? `- ${result.action_input}` : ""}</p>
              </div>
              <div>
                <label>Expected Facts</label>
                <div className="chips">{result.expected_facts.map((fact) => <span key={fact}>{fact}</span>)}</div>
              </div>
              <div>
                <label>Retrieved Context</label>
                <p>{result.retrieved_chunks[0] ?? "No retrieved context."}</p>
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
  const [selectedRun, setSelectedRun] = useState<RunDetail | null>(null);
  const [mode, setMode] = useState<"mock" | "claude">("mock");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    const [nextSummary, nextRuns] = await Promise.all([
      api<Summary>("/api/summary"),
      api<EvalRun[]>("/api/runs"),
    ]);
    setSummary(nextSummary);
    setRuns(nextRuns);
    if (nextSummary.latest_run) {
      setSelectedRun(await api<RunDetail>(`/api/runs/${nextSummary.latest_run.id}`));
    }
  }

  async function runEval() {
    setLoading(true);
    setError(null);
    try {
      const detail = await api<RunDetail>("/api/runs", {
        method: "POST",
        body: JSON.stringify({ mode }),
      });
      setSelectedRun(detail);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh().catch((err) => setError(err instanceof Error ? err.message : "Unable to load dashboard"));
  }, []);

  const failed = selectedRun?.results.filter((result) => !result.passed) ?? summary?.failed_cases ?? [];
  const latestLabel = useMemo(() => {
    if (!summary?.latest_run) return "No runs yet";
    return `Run ${summary.latest_run.id} - ${new Date(summary.latest_run.created_at).toLocaleString()}`;
  }, [summary]);

  return (
    <main>
      <header className="topbar">
        <div>
          <h1>AgentEval Harness</h1>
          <p>Evaluation dashboard for RAG and tool-using document agents.</p>
        </div>
        <div className="controls">
          <div className="segmented" aria-label="Agent mode">
            <button className={mode === "mock" ? "active" : ""} onClick={() => setMode("mock")}>Mock</button>
            <button className={mode === "claude" ? "active" : ""} onClick={() => setMode("claude")}>Claude</button>
          </div>
          <button className="secondary" onClick={() => refresh()} title="Refresh dashboard">
            <RefreshCw size={16} />
          </button>
          <button className="primary" onClick={runEval} disabled={loading}>
            <Play size={16} />
            {loading ? "Running" : "Run evals"}
          </button>
        </div>
      </header>

      {error && <div className="error"><AlertTriangle size={16} />{error}</div>}

      <section className="metricsGrid">
        <MetricCard label="Tests Run" value={String(summary?.total_tests_run ?? 0)} helper={`${summary?.total_runs ?? 0} total runs`} icon={<Target size={18} />} />
        <MetricCard label="Pass Rate" value={pct(summary?.pass_rate ?? 0)} helper={latestLabel} icon={<CheckCircle2 size={18} />} />
        <MetricCard label="Avg Latency" value={`${Math.round(summary?.avg_latency_ms ?? 0)} ms`} helper="Latest run average" icon={<Clock3 size={18} />} />
        <MetricCard label="Avg Cost" value={money(summary?.avg_cost_usd ?? 0)} helper="Per case estimate" icon={<WalletCards size={18} />} />
      </section>

      <section className="contentGrid">
        <div className="panel">
          <div className="panelHead">
            <h2>Failed Cases</h2>
            <span>{failed.length} failing</span>
          </div>
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th />
                  <th>Case</th>
                  <th>Failure</th>
                  <th>Answer</th>
                  <th>Tool</th>
                  <th>Latency</th>
                </tr>
              </thead>
              <tbody>
                {failed.length ? failed.map((result) => <ResultRow key={result.id} result={result} />) : (
                  <tr><td colSpan={6} className="emptyCell">Run the suite to inspect failures.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <aside className="sideStack">
          <div className="panel">
            <div className="panelHead">
              <h2>Failure Types</h2>
            </div>
            <FailureBreakdown counts={summary?.failure_counts ?? {}} />
          </div>
          <div className="panel">
            <div className="panelHead">
              <h2>Recent Runs</h2>
            </div>
            <div className="runList">
              {runs.map((run) => (
                <button key={run.id} onClick={async () => setSelectedRun(await api<RunDetail>(`/api/runs/${run.id}`))}>
                  <b>Run {run.id}</b>
                  <span>{run.mode} - {pct(run.pass_rate)} - {run.total_cases} cases</span>
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

