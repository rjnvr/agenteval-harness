export type Provider = "mock" | "naive" | "anthropic" | "openai" | "google" | "openrouter" | "webhook";

export type EvalRun = {
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

export type ScoreBreakdown = {
  decision_correctness: number;
  constraint_satisfaction: number;
  preference_adherence: number;
  timezone_accuracy: number;
  coordination_coverage: number;
};

export type EvalResult = {
  id: number;
  case_id: string;
  document_name: string;
  question: string;
  expected_answer: string;
  expected_facts: string[];
  matched_facts: string[];
  missed_facts: string[];
  expected_action: string;
  acceptable_actions: string[];
  context: Record<string, unknown>;
  expected_decision: Record<string, unknown>;
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
  slot_valid: boolean;
  preference_score: number;
  timezone_correct: boolean;
  proposed_slot: string;
  unsupported_claims: string[];
  latency_ms: number;
  cost_usd: number;
  failure_type: string;
  failure_mode: string;
  failure_explanation: string;
  passed: boolean;
  retrieved_chunks: string[];
  trace: Record<string, unknown>;
  score_breakdown: ScoreBreakdown;
};

export type RunDetail = EvalRun & { results: EvalResult[] };

export type Summary = {
  total_runs: number;
  total_tests_run: number;
  latest_run: EvalRun | null;
  pass_rate: number;
  avg_latency_ms: number;
  avg_cost_usd: number;
  failure_counts: Record<string, number>;
  failed_cases: EvalResult[];
  score_breakdown: ScoreBreakdown;
  calibration: { sample_size: number; pass_agreement: number; pass_kappa: number; failure_mode_agreement: number; threshold: number };
  pii_redaction: { expected_entities: number; redacted_entities: number; recall: number };
};

export type ComparisonRun = {
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
  strict_pass_rate: number;
  score_breakdown: ScoreBreakdown;
  avg_semantic_quality: number;
  avg_fact_completeness: number;
  avg_tool_accuracy: number;
  avg_grounding: number;
  avg_retrieval_quality: number;
  avg_decision_correctness: number;
  avg_constraint_satisfaction: number;
  avg_preference_adherence: number;
  avg_timezone_accuracy: number;
  avg_coordination_coverage: number;
  failure_counts: Record<string, number>;
  failed_cases: { case_id: string; failure_mode: string; answer_match: number }[];
};

export type Comparison = { runs: ComparisonRun[] };

export type EvalSummary = {
  run_id: number;
  provider: Provider;
  model: string;
  summary: string;
};
