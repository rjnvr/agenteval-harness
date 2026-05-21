import type { ComparisonRun } from "../types";
import { money, pct, providerLabel, topFailure } from "../utils";

export function ComparisonPanel({ runs, onSelectRun }: { runs: ComparisonRun[]; onSelectRun: (id: number) => void }) {
  if (!runs.length) {
    return (
      <section className="panel comparisonPanel">
        <div className="panelHead"><h2>LLM Comparison</h2><span>No runs yet</span></div>
        <div className="emptyBand">Run two or more model evaluations to compare results.</div>
      </section>
    );
  }
  const bestPassRate = Math.max(...runs.map((run) => run.pass_rate));
  const bestSemantic = Math.max(...runs.map((run) => run.avg_semantic_quality ?? run.avg_answer_match));
  return (
    <section className="panel comparisonPanel">
      <div className="panelHead"><h2>LLM Comparison</h2><span>{runs.length} recent runs</span></div>
      <div className="compareCards">
        {runs.slice(0, 4).map((run) => (
          <button className="compareCard" key={run.id} onClick={() => onSelectRun(run.id)}>
            <span>{providerLabel(run.provider)}</span>
            <b>{run.model}</b>
            <strong>{pct(run.pass_rate)}</strong>
            <em>Strict pass</em>
            <small>{pct(run.avg_semantic_quality ?? run.avg_answer_match)} answer quality - {pct(run.avg_grounding ?? run.avg_groundedness)} grounded</small>
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
              <th>Quality</th>
              <th>Facts</th>
              <th>Tools</th>
              <th>Grounding</th>
              <th>Retrieval</th>
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
                <td><b className={(run.avg_semantic_quality ?? run.avg_answer_match) === bestSemantic ? "bestMetric" : ""}>{pct(run.avg_semantic_quality ?? run.avg_answer_match)}</b></td>
                <td>{pct(run.avg_fact_completeness ?? run.avg_fact_recall)}</td>
                <td>{pct(run.avg_tool_accuracy ?? 0)}</td>
                <td>{pct(run.avg_grounding ?? run.avg_groundedness)}</td>
                <td>{pct(run.avg_retrieval_quality ?? 0)}</td>
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
