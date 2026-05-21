import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { EvalResult } from "../types";
import { pct } from "../utils";
import { FactChips } from "./FactChips";
import { ScorePill } from "./ScorePill";

export function ResultRow({ result }: { result: EvalResult }) {
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
                <ScorePill label="Quality" value={pct(result.score_breakdown.semantic_quality)} />
                <ScorePill label="Tool score" value={pct(result.score_breakdown.tool_accuracy)} />
                <ScorePill label="Retrieval" value={pct(result.score_breakdown.retrieval_quality)} />
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
